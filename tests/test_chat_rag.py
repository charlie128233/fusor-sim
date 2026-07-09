"""Test di RAG e pipeline chat. L'LLM è un finto iniettato: qui si
verifica la meccanica (retrieval, parsing, gating, validazione),
non la qualità del modello."""

import json
from pathlib import Path

import pytest

from fusor_sim.chat.pipeline import ChatPipeline, _extract_json
from fusor_sim.orchestrator import Orchestrator, OrchestratorState
from fusor_sim.rag import KnowledgeBase

KNOWLEDGE = Path(__file__).parent.parent / "knowledge"


@pytest.fixture()
def kb():
    return KnowledgeBase(KNOWLEDGE)


# ------------------------------------------------------------------ RAG


def test_retrieval_finds_lawson(kb):
    hits = kb.search("quanto siamo lontani dalla soglia del criterio di Lawson?")
    assert hits
    assert hits[0].source == "lawson"


def test_retrieval_finds_grid_losses(kb):
    hits = kb.search("perché la griglia catodica intercetta gli ioni e domina le perdite")
    assert hits[0].source in ("fusore", "bilancio_potenza")


def test_retrieval_scores_ordered(kb):
    hits = kb.search("trasparenza della griglia")
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------- JSON parsing


def test_extract_json_tolerates_prose():
    raw = 'Ecco: {"reply": "ok", "intents": []} spero vada bene'
    assert _extract_json(raw)["reply"] == "ok"


def test_extract_json_garbage_gives_empty():
    assert _extract_json("nessun json qui") == {}


# ------------------------------------------------------------- pipeline


def _fake_llm(payload: dict):
    def llm(messages):
        return json.dumps(payload)

    return llm


def test_pipeline_applies_valid_intent(kb):
    orch = Orchestrator()
    pipe = ChatPipeline(
        orch,
        kb,
        _fake_llm(
            {
                "reply": "Porto la tensione a -60 kV.",
                "intents": [
                    {"action": "SET", "target": "physics.cathode_voltage_v", "value": -60000}
                ],
                "start_run": False,
            }
        ),
    )
    out = pipe.handle("metti 60 kV")
    assert orch.physics.cathode_voltage_v == -60000
    assert "[ok]" in out.reply
    assert not out.start_run


def test_pipeline_reports_physical_rejection(kb):
    orch = Orchestrator()
    pipe = ChatPipeline(
        orch,
        kb,
        _fake_llm(
            {
                "reply": "Provo.",
                "intents": [
                    {"action": "SET", "target": "physics.pressure_pa", "value": 5000}
                ],
            }
        ),
    )
    out = pipe.handle("pressione a 5000 pascal")
    assert "[RIFIUTATO]" in out.reply
    assert orch.physics.pressure_pa == 0.5  # bozza intatta


def test_pipeline_blocks_autotuner_fields(kb):
    """L'LLM prova a toccare numerics: il contratto lo blocca prima
    dell'orchestratore."""
    orch = Orchestrator()
    pipe = ChatPipeline(
        orch,
        kb,
        _fake_llm(
            {"reply": "ok", "intents": [{"action": "SET", "target": "numerics.dt_s", "value": 1e-12}]}
        ),
    )
    out = pipe.handle("abbassa il passo temporale")
    assert "[RIFIUTATO]" in out.reply
    assert "intent non valido" in out.reply


def test_pipeline_gated_outside_idle_paused(kb):
    orch = Orchestrator()
    orch.prepare(n_particles=1000, max_steps=400, snapshot_interval=200, probe=False)
    assert orch.state is OrchestratorState.CONFIG
    called = []

    def llm(messages):
        called.append(1)
        return "{}"

    pipe = ChatPipeline(orch, kb, llm)
    out = pipe.handle("cambia la pressione")
    assert "CONFIG" in out.reply
    assert not called  # l'LLM non è nemmeno stato chiamato


def test_pipeline_survives_non_json_llm(kb):
    orch = Orchestrator()
    pipe = ChatPipeline(orch, kb, lambda m: "Risposta libera senza JSON")
    out = pipe.handle("ciao")
    assert "Risposta libera" in out.reply
    assert out.intent_results == []


def test_pipeline_start_run_flag(kb):
    orch = Orchestrator()
    pipe = ChatPipeline(
        orch, kb, _fake_llm({"reply": "Avvio.", "intents": [], "start_run": True})
    )
    assert pipe.handle("simula!").start_run


def test_pipeline_offset_and_preview_flag(kb):
    """Lo spostamento del catodo via LLM: accettato in bozza, con flag
    per l'anteprima di campo; la config diventa non giudicabile."""
    orch = Orchestrator()
    pipe = ChatPipeline(
        orch,
        kb,
        _fake_llm(
            {
                "reply": "Sposto il catodo di 2 cm; configurazione non giudicabile, mostro il campo.",
                "intents": [
                    {"action": "SET", "target": "geometry.cathode_offset_x_m", "value": 0.02}
                ],
                "preview_field": True,
            }
        ),
    )
    out = pipe.handle("sposta il catodo 2 cm a destra")
    assert out.preview_field
    assert orch.geometry.cathode_offset_x_m == 0.02
    assert not orch.judgeable()[0]


def test_pipeline_selected_component_in_context(kb):
    orch = Orchestrator()
    seen = {}

    def llm(messages):
        seen["ctx"] = messages[0]["content"]
        return '{"reply": "ok", "intents": []}'

    ChatPipeline(orch, kb, llm).handle("rendila più piccola", selected_component="catodo")
    assert "COMPONENTE SELEZIONATO" in seen["ctx"]
    assert "catodo" in seen["ctx"]


def test_pipeline_feeds_verdict_to_llm(kb):
    """Se esiste un referto, l'LLM lo riceve nel contesto come verità."""
    orch = Orchestrator()
    orch.prepare(n_particles=1000, max_steps=400, snapshot_interval=200, probe=False)
    orch.start()
    while orch.state is OrchestratorState.RUN:
        orch.advance()
    orch.reset()

    seen = {}

    def llm(messages):
        seen["context"] = "\n".join(m["content"] for m in messages)
        return json.dumps({"reply": "ok", "intents": []})

    ChatPipeline(orch, kb, llm).handle("perché il bilancio è negativo?")
    assert "ULTIMO REFERTO" in seen["context"]
    assert "Lawson" in seen["context"]
