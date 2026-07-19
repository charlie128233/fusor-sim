"""Pipeline chat: messaggio utente -> LLM -> ChatIntent -> orchestratore.

La gerarchia dei ruoli è applicata qui:
- l'LLM PROPONE (emette intent in JSON) e SPIEGA (citando il RAG);
- ogni intent passa dalla validazione contratto + orchestratore, che può
  rifiutarlo: il rifiuto, col motivo fisico, torna all'utente;
- l'LLM non vede mai il motore, solo bozza di configurazione e referti.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import ValidationError

from fusor_sim.contracts.chat_intent import ChatIntent
from fusor_sim.orchestrator import IntentResult, Orchestrator, OrchestratorState
from fusor_sim.rag import KnowledgeBase

_SYSTEM_PROMPT = """Sei l'assistente di un simulatore didattico di fusione \
(fusore Farnsworth-Hirsch). Il tuo ruolo: PROPORRE configurazioni e SPIEGARE \
i risultati. Non sei mai tu a giudicare la fisica: il giudice è il simulatore, \
e il suo referto (physics_verdict) è la verità. Non promettere mai che una \
configurazione "funzionerà": al massimo che vale la pena provarla.

Parametri modificabili (azione SET o SCALE), con range validi:
- physics.cathode_voltage_v: tensione catodo, NEGATIVA, da -500000 a 0 (V)
- physics.pressure_pa: pressione gas, da 0.0001 a 100 (Pa)
- physics.gas_species: "D-D" oppure "D-T"
- physics.ion_source_rate_per_s: ioni/s dalla sorgente, fino a 1e22
- physics.gas_temperature_k: temperatura gas, fino a 2000 (K)
- geometry.cathode_radius_m: raggio griglia interna (m)
- geometry.anode_radius_m: raggio griglia esterna (m), > catodo
- geometry.chamber_radius_m: raggio camera (m), >= anodo
- geometry.grid_transparency: trasparenza griglia, tra 0 e 1 esclusi
- geometry.cathode_offset_x_m / _y_m / _z_m: spostamento del catodo dal \
centro (m, default 0). ATTENZIONE: con offset diverso da 0 la configurazione \
NON è giudicabile per la fusione (nessun solver nel catalogo la copre): è \
disponibile solo l'anteprima 3D del campo elettrostatico. Dichiaralo sempre.
I parametri numerici (numerics.*) e i solver NON si toccano: appartengono \
all'auto-tuner e al router.

Esiste anche il DOMINIO TOKAMAK (modello 0D + equilibrio Grad-Shafranov), \
parametri modificabili:
- tokamak_geometry.major_radius_m: raggio maggiore R0 (0.3-12 m)
- tokamak_geometry.minor_radius_m: raggio minore a (< R0/1.5)
- tokamak_geometry.elongation: elongazione kappa (1-2.5)
- tokamak_geometry.toroidal_field_t: campo toroidale B0 (0.5-14 T)
- tokamak_geometry.plasma_current_ma: corrente di plasma (0.1-20 MA)
- tokamak_physics.density_1e19_m3: densità (0.1-50, in 1e19 m^-3)
- tokamak_physics.aux_heating_mw: riscaldamento ausiliario (0-200 MW)
- tokamak_physics.h_factor: fattore H di confinamento (0.5-1.5)
Se l'utente vuole passare al tokamak (o tornare al fusore), usa il campo \
"switch_domain". Gli intent tokamak_* funzionano solo nel dominio tokamak.

Rispondi SOLO con un oggetto JSON, nessun testo fuori dal JSON:
{
  "reply": "risposta in italiano per l'utente",
  "intents": [
    {"action": "SET|SCALE|ADD_CONSTRAINT|QUERY", "target": "gruppo.campo",
     "value": <numero o stringa>, "rationale": "eventuale fonte citata"}
  ],
  "start_run": true|false,
  "preview_field": true|false,
  "switch_domain": null | "fusor" | "tokamak"
}
- intents vuoto se l'utente chiede solo spiegazioni.
- SCALE usa un fattore numerico (es. 2 per raddoppiare).
- start_run true solo se l'utente chiede esplicitamente di simulare/avviare.
- preview_field true se l'utente vuole vedere il campo (o dopo aver spostato \
il catodo, per mostrare l'effetto).
- Se nella scena 3D c'è un componente selezionato, i pronomi ("questo", \
"rendila più piccola") si riferiscono a quello.
- Nelle spiegazioni cita gli estratti forniti quando pertinenti.

C'è una GUIDA DIDATTICA integrata (pannello "Guida") con 9 lezioni, dalla \
base alla padronanza: 0 perché la fusione, 1 anatomia del fusore, 2 leggere \
il referto, 3 esperimenti sui parametri, 4 la griglia e le perdite, 5 barriera \
coulombiana e Lawson, 6 geometria e campo 3D, 7 onestà numerica e limiti del \
modello, 8 oltre il fusore (tokamak). Fai da tutor: se una domanda rivela una \
lacuna, suggerisci la lezione pertinente; se l'utente segue un esperimento \
della guida, aiutalo a interpretare i risultati confrontandoli con le attese. \
Se chiede un quiz, fanne uno basato sugli estratti, correggendo con i numeri \
del referto quando disponibili.
"""


@dataclass
class ChatOutcome:
    reply: str
    intent_results: list[tuple[str, IntentResult]] = field(default_factory=list)
    start_run: bool = False
    preview_field: bool = False
    switch_domain: str | None = None
    sources: list[str] = field(default_factory=list)


class ChatPipeline:
    def __init__(
        self,
        orchestrator: Orchestrator,
        knowledge: KnowledgeBase,
        llm: Callable[[list[dict]], str],
    ):
        self.orchestrator = orchestrator
        self.knowledge = knowledge
        self.llm = llm

    def handle(self, message: str, selected_component: str | None = None) -> ChatOutcome:
        orch = self.orchestrator
        if orch.state is OrchestratorState.DONE:
            # run concluso: si torna a IDLE conservando bozza, vincoli e
            # ultimo referto — è il momento di discutere i risultati
            orch.reset()
        if orch.state not in (OrchestratorState.IDLE, OrchestratorState.PAUSED):
            return ChatOutcome(
                reply=(
                    f"La simulazione è in stato {orch.state.value.upper()}: la chat "
                    "può intervenire solo a simulazione ferma o in pausa. "
                    "Metti in pausa o attendi la fine del run."
                )
            )

        passages = self.knowledge.search(message, k=3)
        try:
            raw = self.llm(self._messages(message, passages, selected_component))
        except Exception as exc:  # LLM giù o in errore: l'app resta usabile
            return ChatOutcome(
                reply=(
                    "L'LLM non è raggiungibile o ha risposto con un errore "
                    f"({exc.__class__.__name__}). Puoi comunque usare i comandi "
                    "manuali del pannello; la simulazione non dipende dall'LLM."
                )
            )
        data = _extract_json(raw)
        reply = str(data.get("reply") or raw).strip()

        switch = data.get("switch_domain")
        if switch in ("fusor", "tokamak") and switch != orch.domain:
            orch.set_domain(switch)
            reply += f"\n[dominio: {switch}]"
        else:
            switch = None

        results: list[tuple[str, IntentResult]] = []
        for item in data.get("intents", []):
            label, result = self._apply(item)
            results.append((label, result))

        lines = [reply]
        for label, result in results:
            mark = "[ok]" if result.accepted else "[RIFIUTATO]"
            lines.append(f"{mark} {label}: {result.message}")
        return ChatOutcome(
            reply="\n".join(lines),
            intent_results=results,
            start_run=bool(data.get("start_run")),
            preview_field=bool(data.get("preview_field")),
            switch_domain=switch,
            sources=sorted({p.source for p in passages}),
        )

    # ------------------------------------------------------------ interni

    def _messages(
        self, message: str, passages, selected_component: str | None = None
    ) -> list[dict]:
        orch = self.orchestrator
        context = [
            f"STATO ORCHESTRATORE: {orch.state.value}",
            f"DOMINIO ATTIVO: {orch.domain}",
        ]
        if orch.domain == "tokamak":
            context.append(
                "CONFIGURAZIONE TOKAMAK (bozza): "
                f"tokamak_geometry={orch.tokamak_geometry.model_dump()} "
                f"tokamak_physics={orch.tokamak_physics.model_dump()}"
            )
        else:
            context.append(
                "CONFIGURAZIONE ATTUALE (bozza): "
                f"geometry={orch.geometry.model_dump()} "
                f"physics={orch.physics.model_dump()}"
            )
        judgeable, reason = orch.judgeable()
        if not judgeable:
            context.append(f"CONFIGURAZIONE NON GIUDICABILE: {reason}")
        if selected_component:
            context.append(
                f"COMPONENTE SELEZIONATO NELLA SCENA 3D: {selected_component}"
            )
        if orch.constraints:
            context.append(
                "VINCOLI ATTIVI: " + "; ".join(c.describe() for c in orch.constraints)
            )
        if orch.last_state is not None:
            v = orch.last_state.physics_verdict
            context.append(
                "ULTIMO REFERTO DEL SIMULATORE (la verità, non contraddirlo): "
                + v.honest_summary
            )
        if passages:
            context.append(
                "ESTRATTI DAL LIBRO DELLE FORMULE:\n"
                + "\n---\n".join(f"[{p.source}] {p.text}" for p in passages)
            )
        # un solo messaggio system: alcuni server locali rifiutano i doppioni
        return [
            {"role": "system", "content": _SYSTEM_PROMPT + "\n\n" + "\n\n".join(context)},
            {"role": "user", "content": message},
        ]

    def _apply(self, item: dict) -> tuple[str, IntentResult]:
        label = f"{item.get('action', '?')} {item.get('target') or ''}".strip()
        try:
            intent = ChatIntent(
                action=str(item.get("action", "")).upper(),
                target=item.get("target"),
                value=item.get("value"),
                rationale=item.get("rationale"),
            )
        except ValidationError as exc:
            reason = "; ".join(e["msg"] for e in exc.errors())
            return label, IntentResult(False, f"intent non valido: {reason}")
        return label, self.orchestrator.apply_intent(intent)


def _extract_json(raw: str) -> dict:
    """Estrae il primo oggetto JSON dalla risposta dell'LLM, con tolleranza."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}
