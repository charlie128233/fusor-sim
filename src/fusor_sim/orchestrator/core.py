"""State machine dell'orchestratore.

Garanzie strutturali (non convenzioni):
- gli intent della chat sono accettati SOLO in IDLE e PAUSED;
- il motore avanza SOLO in RUN (advance), dove nessun intent è accettato:
  interagire col loop caldo è impossibile per costruzione;
- la RunConfig è emessa solo da prepare(), mai in RUN;
- ogni modifica passa dalla validazione dei contratti (range fisici,
  geometrie realizzabili) e dai vincoli espliciti accumulati
  (ADD_CONSTRAINT, domani il catalogo componenti reali).
"""

import re
from dataclasses import dataclass, field
from enum import Enum

from pydantic import ValidationError

from fusor_sim.catalog import get_field_solver, get_pusher_class
from fusor_sim.contracts.chat_intent import ChatAction, ChatIntent
from fusor_sim.contracts.field_preview import FieldPreview
from fusor_sim.contracts.physics_verdict import (
    LossBreakdown,
    NumericalReliability,
    PhysicsVerdict,
)
from fusor_sim.contracts.run_config import (
    GeometryConfig,
    PhysicsConfig,
    RunConfig,
    RunControl,
    StopCondition,
    example_run_config,
)
from fusor_sim.contracts.sim_state import RunStatus, SimState
from fusor_sim.orchestrator.autotuner import tune_numerics
from fusor_sim.orchestrator.router import select_solvers

_FIELD_PREVIEW_SOLVER_ID = "poisson_cartesian3d_fd_v1"


class OrchestratorState(str, Enum):
    IDLE = "idle"
    CONFIG = "config"
    RUN = "run"
    PAUSED = "paused"
    DONE = "done"


class StateError(RuntimeError):
    """Operazione non consentita nello stato corrente."""


@dataclass(frozen=True)
class IntentResult:
    accepted: bool
    message: str


_OP_FUNCS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}
_CONSTRAINT_RE = re.compile(r"^\s*(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*$")


@dataclass(frozen=True)
class Constraint:
    """Vincolo esplicito su un campo, es. dal catalogo componenti:
    'l'alimentatore arriva a 30 kV' -> cathode_voltage_v >= -30000."""

    target: str
    op: str
    bound: float
    source: str = ""

    def satisfied_by(self, value: float) -> bool:
        return _OP_FUNCS[self.op](value, self.bound)

    def describe(self) -> str:
        origin = f" (fonte: {self.source})" if self.source else ""
        return f"{self.target} {self.op} {self.bound:g}{origin}"


@dataclass
class Orchestrator:
    geometry: GeometryConfig = field(
        default_factory=lambda: example_run_config().geometry
    )
    physics: PhysicsConfig = field(
        default_factory=lambda: example_run_config().physics
    )
    seed: int = 0

    def __post_init__(self) -> None:
        self.state = OrchestratorState.IDLE
        self.constraints: list[Constraint] = []
        self.formula_sources: list[str] = []
        self.run_config: RunConfig | None = None
        self.last_state: SimState | None = None
        self.run_states: list[SimState] = []
        self.history: list[str] = [f"stato iniziale: {self.state.value}"]
        self._engine_iter = None

    # ------------------------------------------------------ chat gateway

    def apply_intent(self, intent: ChatIntent) -> IntentResult:
        """Unico punto d'ingresso per le proposte della chat."""
        if self.state not in (OrchestratorState.IDLE, OrchestratorState.PAUSED):
            raise StateError(
                f"La chat può proporre modifiche solo in IDLE o PAUSED, "
                f"non in {self.state.value.upper()}"
            )
        handler = {
            ChatAction.SET: self._handle_set,
            ChatAction.SCALE: self._handle_scale,
            ChatAction.QUERY: self._handle_query,
            ChatAction.ADD_CONSTRAINT: self._handle_add_constraint,
            ChatAction.ADD_FORMULA_SOURCE: self._handle_add_source,
        }[intent.action]
        result = handler(intent)
        self.history.append(
            f"intent {intent.action.value} {intent.target or ''}: "
            f"{'ok' if result.accepted else 'RIFIUTATO'} - {result.message}"
        )
        return result

    def _handle_set(self, intent: ChatIntent) -> IntentResult:
        return self._patch_draft(intent.target, intent.value)

    def _handle_scale(self, intent: ChatIntent) -> IntentResult:
        old = self._get_value(intent.target)
        if not isinstance(old, (int, float)) or isinstance(old, bool):
            return IntentResult(False, f"'{intent.target}' non è scalabile")
        return self._patch_draft(intent.target, old * intent.value)

    def _handle_query(self, intent: ChatIntent) -> IntentResult:
        if intent.target:
            try:
                return IntentResult(
                    True, f"{intent.target} = {self._get_value(intent.target)}"
                )
            except (AttributeError, ValueError):
                return IntentResult(
                    False, f"'{intent.target}' non è un parametro interrogabile"
                )
        return IntentResult(
            True,
            f"geometry={self.geometry.model_dump()} physics={self.physics.model_dump()}",
        )

    def _handle_add_constraint(self, intent: ChatIntent) -> IntentResult:
        if not intent.target or not isinstance(intent.value, str):
            return IntentResult(
                False, "ADD_CONSTRAINT richiede target e value tipo '>= -30000'"
            )
        m = _CONSTRAINT_RE.match(intent.value)
        if not m:
            return IntentResult(
                False, f"vincolo '{intent.value}' non riconosciuto (atteso: '<op> <numero>')"
            )
        try:
            current = self._get_value(intent.target)
        except (AttributeError, ValueError):
            return IntentResult(
                False, f"'{intent.target}' non è un parametro vincolabile"
            )
        constraint = Constraint(
            target=intent.target,
            op=m.group(1),
            bound=float(m.group(2)),
            source=intent.rationale or "",
        )
        if isinstance(current, (int, float)) and not constraint.satisfied_by(current):
            return IntentResult(
                False,
                f"il valore attuale {intent.target}={current} viola già "
                f"{constraint.describe()}: modificare prima il parametro",
            )
        self.constraints.append(constraint)
        return IntentResult(True, f"vincolo aggiunto: {constraint.describe()}")

    def _handle_add_source(self, intent: ChatIntent) -> IntentResult:
        self.formula_sources.append(intent.value)
        return IntentResult(True, f"fonte registrata per il RAG: {intent.value}")

    # ----------------------------------------------------- ciclo di vita

    def prepare(
        self,
        *,
        n_particles: int = 20_000,
        max_steps: int = 20_000,
        snapshot_interval: int = 1_000,
        stop_conditions: tuple[StopCondition, ...] = (),
        probe: bool = True,
    ) -> RunConfig:
        """IDLE/PAUSED/DONE/CONFIG -> CONFIG: router + auto-tuner + RunConfig."""
        if self.state is OrchestratorState.RUN:
            raise StateError("Impossibile emettere una RunConfig durante RUN")
        if self.state is OrchestratorState.PAUSED:
            self.history.append("run in pausa scartato per riconfigurazione")
        self._discard_engine()

        violated = [
            c
            for c in self.constraints
            if isinstance(self._get_value(c.target), (int, float))
            and not c.satisfied_by(self._get_value(c.target))
        ]
        if violated:
            raise StateError(
                "Configurazione in violazione dei vincoli: "
                + "; ".join(c.describe() for c in violated)
            )

        solver_selection = select_solvers(self.geometry)
        numerics = tune_numerics(
            self.geometry,
            self.physics,
            solver_selection,
            n_particles=n_particles,
            probe=probe,
            seed=self.seed,
        )
        self.run_config = RunConfig(
            geometry=self.geometry,
            physics=self.physics,
            numerics=numerics,
            solver_selection=solver_selection,
            run_control=RunControl(
                max_steps=max_steps,
                snapshot_interval=snapshot_interval,
                checkpoint_interval=max_steps,
                stop_conditions=stop_conditions,
            ),
        )
        self._transition(OrchestratorState.CONFIG)
        return self.run_config

    def start(self) -> None:
        if self.state is not OrchestratorState.CONFIG:
            raise StateError(f"start() richiede CONFIG, stato attuale {self.state.value}")
        engine_cls = get_pusher_class(self.run_config.solver_selection.pusher_id)
        engine = engine_cls(self.run_config, seed=self.seed)
        self._engine_iter = engine.run()
        self.run_states = []
        self._transition(OrchestratorState.RUN)

    def advance(self, snapshots: int = 1) -> list[SimState]:
        """Avanza il run di N snapshot. Unico punto che tocca il motore."""
        if self.state is not OrchestratorState.RUN:
            raise StateError(f"advance() richiede RUN, stato attuale {self.state.value}")
        pulled: list[SimState] = []
        for _ in range(snapshots):
            try:
                state = next(self._engine_iter)
            except StopIteration:
                break
            pulled.append(state)
            self.run_states.append(state)
            self.last_state = state
            if state.meta.status is RunStatus.DONE:
                break
        if self.last_state and self.last_state.meta.status is RunStatus.DONE:
            self._transition(OrchestratorState.DONE)
        elif not pulled:
            self._transition(OrchestratorState.DONE)
        return pulled

    def pause(self) -> None:
        if self.state is not OrchestratorState.RUN:
            raise StateError("pause() richiede RUN")
        self._transition(OrchestratorState.PAUSED)

    def resume(self) -> None:
        if self.state is not OrchestratorState.PAUSED:
            raise StateError("resume() richiede PAUSED")
        self._transition(OrchestratorState.RUN)

    def reset(self) -> None:
        """Torna a IDLE mantenendo la bozza (geometry/physics) e i vincoli."""
        self._discard_engine()
        self.run_config = None
        self._transition(OrchestratorState.IDLE)

    def factory_reset(self) -> None:
        """Reimposta il progetto: bozza ai default, vincoli e fonti azzerati."""
        self._discard_engine()
        defaults = example_run_config()
        self.geometry = defaults.geometry
        self.physics = defaults.physics
        self.constraints = []
        self.formula_sources = []
        self.run_config = None
        self.last_state = None
        self.run_states = []
        self.history.append("progetto reimpostato ai valori di fabbrica")
        self._transition(OrchestratorState.IDLE)

    # ------------------------------------------------- anteprima di campo

    def judgeable(self) -> tuple[bool, str]:
        """La bozza attuale è giudicabile (esiste un solver per la fusione)?"""
        try:
            select_solvers(self.geometry)
            return True, ""
        except ValueError as exc:
            return False, str(exc)

    def field_preview(self, n_nodes: int = 64) -> FieldPreview:
        """Anteprima 3D del solo campo elettrostatico sulla bozza attuale.

        Permessa in ogni stato tranne RUN (non tocca il motore, ma è pur
        sempre calcolo su richiesta dell'interfaccia).
        """
        if self.state is OrchestratorState.RUN:
            raise StateError("Anteprima di campo non disponibile durante RUN")
        solver = get_field_solver(_FIELD_PREVIEW_SOLVER_ID)
        field = solver.solve(self.geometry, self.physics.cathode_voltage_v, n_nodes)

        ok, reason = self.judgeable()
        if not field.converged:
            reliability = NumericalReliability.UNRELIABLE
            quality = (
                f"ATTENZIONE: il solve del campo NON è converso (residuo "
                f"{field.residual_rel:.2e}): il campo mostrato non è affidabile."
            )
        else:
            reliability = NumericalReliability.RELIABLE
            quality = (
                f"Campo risolto (residuo {field.residual_rel:.2e}, "
                f"{field.iterations} iterazioni CG)."
            )
        judgement = (
            "Configurazione concentrica: per il giudizio di fusione avvia un run."
            if ok
            else f"Configurazione NON giudicabile per la fusione: {reason}"
        )
        verdict = PhysicsVerdict(
            scope="field_only",
            numerical_reliability=reliability,
            produces_fusion=None,
            fusion_rate_per_s=None,
            fusion_power_w=None,
            input_power_w=0.0,
            net_energy_balance_w=None,
            loss_breakdown=LossBreakdown(
                grid_w=0.0, radiation_w=0.0, conduction_w=0.0, escape_w=0.0
            ),
            lawson_distance_orders=None,
            honest_summary=(
                "Anteprima del SOLO campo elettrostatico: nessuna dinamica "
                f"particellare, nessun numero di fusione. {quality} {judgement}"
            ),
        )
        n = len(field.axis_m)
        preview = FieldPreview(
            grid_extent_m=self.geometry.anode_radius_m,
            n_nodes=n,
            slice_z0_v=field.potential_v[:, :, n // 2],
            slice_y0_v=field.potential_v[:, n // 2, :],
            cathode_offset_m=(
                self.geometry.cathode_offset_x_m,
                self.geometry.cathode_offset_y_m,
                self.geometry.cathode_offset_z_m,
            ),
            converged=field.converged,
            residual_rel=field.residual_rel,
            physics_verdict=verdict,
        )
        self.history.append(
            f"anteprima campo 3D ({n} nodi/lato, converso={field.converged})"
        )
        return preview

    # ---------------------------------------------------------- interni

    def _patch_draft(self, target: str, value) -> IntentResult:
        group_name, field_name = target.split(".", 1)
        for c in self.constraints:
            if c.target == target and isinstance(value, (int, float)):
                if not c.satisfied_by(value):
                    return IntentResult(
                        False, f"violerebbe il vincolo {c.describe()}"
                    )
        group = getattr(self, group_name)
        old = getattr(group, field_name)
        try:
            patched = type(group)(**{**group.model_dump(), field_name: value})
        except ValidationError as exc:
            reason = "; ".join(e["msg"] for e in exc.errors())
            return IntentResult(False, f"rifiutato dai vincoli fisici: {reason}")
        setattr(self, group_name, patched)
        return IntentResult(True, f"{target}: {old} -> {getattr(patched, field_name)}")

    def _get_value(self, target: str):
        group_name, field_name = target.split(".", 1)
        return getattr(getattr(self, group_name), field_name)

    def _discard_engine(self) -> None:
        self._engine_iter = None

    def _transition(self, new: OrchestratorState) -> None:
        self.history.append(f"{self.state.value} -> {new.value}")
        self.state = new
