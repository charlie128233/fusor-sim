"""Server FastAPI del simulatore.

Avvio:  python -m uvicorn fusor_sim.app.server:app --port 8001

Il run gira in un thread di background che chiama orchestrator.advance():
l'interfaccia legge il buffer di snapshot serializzati, non tocca mai il
motore. Un lock serializza ogni accesso all'orchestratore.
"""

import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from fusor_sim.chat import ChatPipeline, LLMClient
from fusor_sim.contracts.sim_state import SimState
from fusor_sim.contracts.tokamak import TokamakState
from fusor_sim.orchestrator import Orchestrator, OrchestratorState, StateError
from fusor_sim.rag import KnowledgeBase

_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent.parent
_KNOWLEDGE_DIR = _ROOT / "knowledge"
_GUIDE_DIR = _ROOT / "guide"


def _guide_lessons() -> list[dict]:
    """Indice della guida didattica: id, titolo, livello, sommario."""
    lessons = []
    for path in sorted(_GUIDE_DIR.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        title = next(
            (l.lstrip("# ").strip() for l in lines if l.startswith("# ")), path.stem
        )
        meta = next((l for l in lines if l.startswith("**Livello:**")), "")
        level = "base"
        if "intermedio" in meta:
            level = "intermedio"
        elif "avanzato" in meta:
            level = "avanzato"
        objective = meta.split("**Obiettivo:**")[-1].strip(" ·") if "Obiettivo" in meta else ""
        lessons.append(
            {"id": path.stem, "title": title, "level": level, "objective": objective}
        )
    return lessons


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    selected_component: str | None = None


class IntentRequest(BaseModel):
    """Intent diretto dall'editor 3D: stesso percorso validato della chat."""

    action: str
    target: str | None = None
    value: float | int | str | bool | None = None


class RunRequest(BaseModel):
    max_steps: int = 20_000
    n_particles: int = 4_000
    snapshot_interval: int = 500
    probe: bool = True


class AppContext:
    def __init__(self, llm: Callable[[list[dict]], str] | None = None):
        self.lock = threading.Lock()
        self.orchestrator = Orchestrator()
        self.llm_client = LLMClient() if llm is None else None
        self.pipeline = ChatPipeline(
            self.orchestrator,
            KnowledgeBase([_KNOWLEDGE_DIR, _GUIDE_DIR]),
            llm if llm is not None else self.llm_client,
        )
        self.snapshot: dict | None = None  # ultimo SimState serializzato
        self.series: list[dict] = []  # serie temporali per i grafici
        self.field_preview: dict | None = None  # ultima anteprima di campo
        self._run_thread: threading.Thread | None = None
        self._llm_ok: bool | None = None
        self._llm_checked_at = 0.0

    def llm_available(self) -> bool:
        """Disponibilità LLM con cache: niente chiamate di rete a ogni poll."""
        if self.llm_client is None:
            return True
        now = time.time()
        if self._llm_ok is None or now - self._llm_checked_at > 10.0:
            self._llm_ok = self.llm_client.available()
            self._llm_checked_at = now
        return self._llm_ok

    # ------------------------------------------------------- run thread

    def start_run(self, req: RunRequest) -> None:
        with self.lock:
            self.orchestrator.prepare(
                n_particles=req.n_particles,
                max_steps=req.max_steps,
                snapshot_interval=req.snapshot_interval,
                probe=req.probe,
            )
            self.orchestrator.start()
            self.series = []
        self._spawn_thread()

    def _spawn_thread(self) -> None:
        self._run_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._run_thread.start()

    def _run_loop(self) -> None:
        while True:
            with self.lock:
                if self.orchestrator.state is not OrchestratorState.RUN:
                    return
                try:
                    pulled = self.orchestrator.advance(1)
                except StateError:
                    return
                for state in pulled:
                    self._record(state)
            time.sleep(0.005)  # lascia respirare le richieste HTTP

    def _record(self, state) -> None:
        d, h = state.diagnostics, state.health
        if isinstance(state, TokamakState):
            self.snapshot = _serialize_tokamak(state)
            self.series.append(
                {
                    "step": state.meta.step,
                    "sim_time_s": state.meta.sim_time_s,
                    "t_kev": d.t_kev,
                    "q_factor": d.q_factor,
                    "fusion_power_w": d.fusion_power_w,
                    "aux_power_w": d.aux_power_w,
                    "tau_e_s": d.tau_e_s,
                    "energy_error": h.energy_conservation_error,
                }
            )
        else:
            self.snapshot = _serialize(state, self.orchestrator)
            self.series.append(
                {
                    "step": state.meta.step,
                    "sim_time_s": state.meta.sim_time_s,
                    "neutron_rate_per_s": d.neutron_rate_per_s,
                    "fusion_rate_per_s": d.fusion_rate_per_s,
                    "grid_loss_w": d.grid_loss_w,
                    "recirculation": d.recirculation_efficiency,
                    "energy_error": h.energy_conservation_error,
                }
            )


def _compute_preview(ctx: AppContext) -> None:
    """Anteprima di campo: il solve (secondi) gira FUORI dal lock — legge
    solo modelli frozen della bozza, e lo stato RUN è comunque rifiutato
    dall'orchestratore."""
    preview = ctx.orchestrator.field_preview()
    serialized = {
        "grid_extent_m": preview.grid_extent_m,
        "n_nodes": preview.n_nodes,
        "slice_z0_v": preview.slice_z0_v.tolist(),
        "slice_y0_v": preview.slice_y0_v.tolist(),
        "cathode_offset_m": list(preview.cathode_offset_m),
        "converged": preview.converged,
        "residual_rel": preview.residual_rel,
        "verdict": preview.physics_verdict.model_dump(mode="json"),
    }
    with ctx.lock:
        ctx.field_preview = serialized


def _serialize_tokamak(state: TokamakState) -> dict:
    d = state.diagnostics
    return {
        "domain": "tokamak",
        "kind": state.kind,
        "meta": {
            "step": state.meta.step,
            "sim_time_s": state.meta.sim_time_s,
            "status": state.meta.status.value,
            "wall_clock_s": state.meta.wall_clock_s,
        },
        "flux": {
            "r_axis_m": state.flux.r_axis_m.tolist(),
            "z_axis_m": state.flux.z_axis_m.tolist(),
            "psi": state.flux.psi.tolist(),
            "psi_boundary": state.flux.psi_boundary,
            "magnetic_axis_r_m": state.flux.magnetic_axis_r_m,
        },
        "diagnostics": {
            "t_kev": d.t_kev,
            "fusion_power_w": d.fusion_power_w,
            "alpha_power_w": d.alpha_power_w,
            "aux_power_w": d.aux_power_w,
            "brems_power_w": d.brems_power_w,
            "transport_power_w": d.transport_power_w,
            "tau_e_s": d.tau_e_s,
            "q_factor": d.q_factor,
            "triple_product_kev_s_m3": d.triple_product_kev_s_m3,
            "neutron_rate_per_s": d.neutron_rate_per_s,
        },
        "health": {
            "energy_conservation_error": state.health.energy_conservation_error,
            "cfl_number": state.health.cfl_number,
            "warnings": list(state.health.warnings),
        },
        "verdict": state.physics_verdict.model_dump(mode="json"),
    }


def _serialize(state: SimState, orch: Orchestrator) -> dict:
    cfg = orch.run_config
    n = len(state.fields.potential_v)
    r = np.linspace(0.0, cfg.geometry.anode_radius_m, n)
    return {
        "domain": "fusor",
        "kind": state.kind,
        "meta": {
            "step": state.meta.step,
            "sim_time_s": state.meta.sim_time_s,
            "status": state.meta.status.value,
            "wall_clock_s": state.meta.wall_clock_s,
        },
        "fields": {
            "r_m": r.tolist(),
            "potential_v": state.fields.potential_v.tolist(),
            "charge_density_c_per_m3": state.fields.charge_density_c_per_m3.tolist(),
        },
        "particles": {
            "r_m": state.particles.positions_m.tolist(),
            "energy_ev": state.particles.energies_ev.tolist(),
        },
        "spectrum": {
            "counts": state.diagnostics.ion_energy_spectrum_ev.tolist(),
            "e_max_ev": 1.2 * abs(cfg.physics.cathode_voltage_v),
        },
        "diagnostics": {
            "fusion_rate_per_s": state.diagnostics.fusion_rate_per_s,
            "neutron_rate_per_s": state.diagnostics.neutron_rate_per_s,
            "grid_loss_w": state.diagnostics.grid_loss_w,
            "recirculation_efficiency": state.diagnostics.recirculation_efficiency,
            "power_balance_w": state.diagnostics.power_balance_w,
        },
        "health": {
            "energy_conservation_error": state.health.energy_conservation_error,
            "cfl_number": state.health.cfl_number,
            "warnings": list(state.health.warnings),
        },
        "verdict": state.physics_verdict.model_dump(mode="json"),
        "geometry": {
            "cathode_radius_m": cfg.geometry.cathode_radius_m,
            "anode_radius_m": cfg.geometry.anode_radius_m,
        },
    }


def create_app(llm: Callable[[list[dict]], str] | None = None) -> FastAPI:
    ctx = AppContext(llm=llm)
    app = FastAPI(title="fusor-sim")
    app.state.ctx = ctx  # esposto per i test

    @app.get("/")
    def index():
        return FileResponse(_HERE / "static" / "index.html")

    @app.get("/api/status")
    def status():
        with ctx.lock:
            orch = ctx.orchestrator
            judgeable, reason = orch.judgeable()
            return {
                "state": orch.state.value,
                "domain": orch.domain,
                "geometry": orch.geometry.model_dump(),
                "physics": orch.physics.model_dump(),
                "tokamak_geometry": orch.tokamak_geometry.model_dump(),
                "tokamak_physics": orch.tokamak_physics.model_dump(),
                "constraints": [c.describe() for c in orch.constraints],
                "judgeable": judgeable,
                "judgeable_reason": reason,
                "last_step": ctx.series[-1]["step"] if ctx.series else None,
                "llm_available": ctx.llm_available(),
            }

    @app.get("/api/snapshot")
    def snapshot():
        with ctx.lock:
            return {
                "snapshot": ctx.snapshot,
                "series": ctx.series,
                "field_preview": ctx.field_preview,
            }

    @app.post("/api/chat")
    def chat(req: ChatRequest):
        with ctx.lock:
            outcome = ctx.pipeline.handle(
                req.message, selected_component=req.selected_component
            )
            if outcome.switch_domain:
                ctx.snapshot = None
                ctx.series = []
                ctx.field_preview = None
        run_started = False
        if outcome.start_run:
            try:
                ctx.start_run(RunRequest())
                run_started = True
            except (StateError, RuntimeError, ValueError) as exc:
                outcome.reply += f"\n[avvio non riuscito: {exc}]"
        preview_done = False
        if outcome.preview_field and not run_started:
            try:
                _compute_preview(ctx)
                preview_done = True
            except (StateError, ValueError) as exc:
                outcome.reply += f"\n[anteprima non riuscita: {exc}]"
        return {
            "reply": outcome.reply,
            "sources": outcome.sources,
            "intents": [
                {"label": label, "accepted": r.accepted, "message": r.message}
                for label, r in outcome.intent_results
            ],
            "run_started": run_started,
            "preview_done": preview_done,
        }

    @app.post("/api/intent")
    def intent(req: IntentRequest):
        """Percorso dell'editor 3D: stessa validazione della chat."""
        from pydantic import ValidationError

        from fusor_sim.contracts.chat_intent import ChatIntent

        try:
            chat_intent = ChatIntent(
                action=req.action.upper(), target=req.target, value=req.value
            )
        except ValidationError as exc:
            reasons = "; ".join(e["msg"] for e in exc.errors())
            return {"accepted": False, "message": f"intent non valido: {reasons}"}
        with ctx.lock:
            try:
                result = ctx.orchestrator.apply_intent(chat_intent)
            except StateError as exc:
                raise HTTPException(status_code=409, detail=str(exc))
        return {"accepted": result.accepted, "message": result.message}

    @app.post("/api/field_preview")
    def field_preview():
        try:
            _compute_preview(ctx)
        except StateError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True, "field_preview": ctx.field_preview}

    @app.post("/api/run")
    def run(req: RunRequest):
        try:
            ctx.start_run(req)
        except (StateError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True}

    @app.post("/api/pause")
    def pause():
        with ctx.lock:
            try:
                ctx.orchestrator.pause()
            except StateError as exc:
                raise HTTPException(status_code=409, detail=str(exc))
        return {"ok": True}

    @app.post("/api/resume")
    def resume():
        with ctx.lock:
            try:
                ctx.orchestrator.resume()
            except StateError as exc:
                raise HTTPException(status_code=409, detail=str(exc))
        ctx._spawn_thread()
        return {"ok": True}

    @app.post("/api/domain")
    def set_domain(payload: dict):
        domain = str(payload.get("domain", ""))
        with ctx.lock:
            try:
                ctx.orchestrator.set_domain(domain)
            except (StateError, ValueError) as exc:
                raise HTTPException(status_code=409, detail=str(exc))
            ctx.snapshot = None
            ctx.series = []
            ctx.field_preview = None
        return {"ok": True, "domain": domain}

    @app.get("/api/guide")
    def guide_index():
        return {"lessons": _guide_lessons()}

    @app.get("/api/guide/{lesson_id}")
    def guide_lesson(lesson_id: str):
        valid = {lesson["id"] for lesson in _guide_lessons()}
        if lesson_id not in valid:
            raise HTTPException(status_code=404, detail=f"Lezione '{lesson_id}' inesistente")
        return {
            "id": lesson_id,
            "markdown": (_GUIDE_DIR / f"{lesson_id}.md").read_text(encoding="utf-8"),
        }

    @app.post("/api/reset")
    def reset():
        with ctx.lock:
            ctx.orchestrator.reset()
            ctx.snapshot = None
            ctx.series = []
            ctx.field_preview = None
        return {"ok": True}

    @app.post("/api/factory_reset")
    def factory_reset():
        """Reimposta il progetto: bozza ai default, vincoli e risultati azzerati."""
        with ctx.lock:
            ctx.orchestrator.factory_reset()
            ctx.snapshot = None
            ctx.series = []
            ctx.field_preview = None
        return {"ok": True}

    return app


app = create_app()
