"""Test del dominio tokamak: reattività Bosch-Hale, equilibrio
Grad-Shafranov validato contro l'analitico, motore 0D e integrazione."""

import numpy as np
import pytest
from pydantic import ValidationError

from fusor_sim.contracts.physics_verdict import NumericalReliability
from fusor_sim.contracts.run_config import RunControl, StopCondition
from fusor_sim.contracts.tokamak import (
    TokamakGeometryConfig,
    TokamakNumericsConfig,
    TokamakPhysicsConfig,
    TokamakRunConfig,
    TokamakSolverSelection,
)
from fusor_sim.engine.fusion import sigmav_dt_m3_s
from fusor_sim.engine.tokamak import Tokamak0DEngine
from fusor_sim.orchestrator import Orchestrator, OrchestratorState, StateError
from fusor_sim.solvers.grad_shafranov import GradShafranovSolver, solovev_from_geometry


def _geometry(**overrides) -> TokamakGeometryConfig:
    base = dict(
        major_radius_m=2.0,
        minor_radius_m=0.6,
        elongation=1.7,
        toroidal_field_t=5.0,
        plasma_current_ma=5.0,
    )
    base.update(overrides)
    return TokamakGeometryConfig(**base)


def _config(geometry=None, physics=None, max_steps=2000, dt=None, **rc) -> TokamakRunConfig:
    geometry = geometry or _geometry()
    physics = physics or TokamakPhysicsConfig(density_1e19_m3=8.0, aux_heating_mw=20.0)
    return TokamakRunConfig(
        geometry=geometry,
        physics=physics,
        numerics=TokamakNumericsConfig(grid_resolution=33, dt_s=dt or 0.002),
        solver_selection=TokamakSolverSelection(
            equilibrium_solver_id="grad_shafranov_solovev_v1",
            engine_id="tokamak_0d_v1",
        ),
        run_control=RunControl(
            max_steps=max_steps,
            snapshot_interval=rc.get("snapshot_interval", max_steps),
            checkpoint_interval=max_steps,
            stop_conditions=rc.get("stop_conditions", ()),
        ),
    )


# ---------------------------------------------------- reattività termica


def test_sigmav_dt_known_values():
    """Bosch-Hale D-T: ~1.1e-22 m^3/s a 10 keV (valore tabulato)."""
    assert sigmav_dt_m3_s(10.0) == pytest.approx(1.13e-22, rel=0.15)
    assert sigmav_dt_m3_s(20.0) == pytest.approx(4.3e-22, rel=0.2)


def test_sigmav_monotonic_below_peak():
    values = [sigmav_dt_m3_s(t) for t in (2, 5, 10, 20, 40, 60)]
    assert all(a < b for a, b in zip(values, values[1:]))


def test_sigmav_zero_outside_validity():
    assert sigmav_dt_m3_s(0.05) == 0.0
    assert sigmav_dt_m3_s(150.0) == 0.0


# ------------------------------------------------------- Grad-Shafranov


def test_gs_matches_analytic_solovev():
    geo = _geometry()
    coeffs = solovev_from_geometry(geo)
    field = GradShafranovSolver().solve(geo, n_nodes=65)
    assert field.converged

    rr, zz = np.meshgrid(field.r_axis_m, field.z_axis_m, indexing="ij")
    exact = coeffs.psi(rr, zz)
    scale = float(np.max(np.abs(exact)))
    err = float(np.max(np.abs(field.psi - exact))) / scale
    assert err < 1e-3  # il problema lineare va riprodotto quasi esattamente

    # asse magnetico vicino a R0
    assert field.magnetic_axis_r_m == pytest.approx(geo.major_radius_m, abs=0.05)


def test_gs_discretization_exact_for_solovev():
    """Per i profili di Solov'ev il flusso (1/R)dpsi/dR è un polinomio di
    grado 2: lo schema centrato lo riproduce ESATTAMENTE — l'errore deve
    essere al livello del residuo CG (~1e-9), non della discretizzazione.
    Questo test ha scovato un bug reale (forma auto-aggiunta sbagliata,
    coefficiente 1/R^2 invece di 1/R) durante lo sviluppo."""
    geo = _geometry()
    coeffs = solovev_from_geometry(geo)
    for n in (33, 65):
        field = GradShafranovSolver().solve(geo, n_nodes=n)
        rr, zz = np.meshgrid(field.r_axis_m, field.z_axis_m, indexing="ij")
        scale = float(np.max(np.abs(coeffs.psi(rr, zz))))
        err = float(np.max(np.abs(field.psi - coeffs.psi(rr, zz)))) / scale
        assert err < 1e-6


# ------------------------------------------------------------ contratti


def test_aspect_ratio_validated():
    with pytest.raises(ValidationError, match="aspetto"):
        _geometry(minor_radius_m=1.5)  # a >= 0.65 * R0


def test_plasma_volume():
    geo = _geometry()
    expected = 2 * np.pi**2 * 2.0 * 0.6**2 * 1.7
    assert geo.plasma_volume_m3 == pytest.approx(expected)


# ------------------------------------------------------------ motore 0D


def test_default_machine_fuses_but_below_breakeven():
    engine = Tokamak0DEngine(_config(max_steps=3000))
    *_, final = engine.run()
    v = final.physics_verdict
    d = final.diagnostics

    assert v.numerical_reliability is not NumericalReliability.UNRELIABLE
    assert v.produces_fusion is True
    assert 0.5 < d.t_kev < 30.0  # temperatura da plasma vero
    assert 0.01 < d.q_factor < 1.0  # fusione reale, sotto il pareggio
    assert v.loss_breakdown.grid_w == 0.0  # nessuna griglia nel plasma
    assert v.loss_breakdown.conduction_w > 0  # il trasporto domina
    assert "griglia" in v.honest_summary
    # a meno di ~2 ordini da Lawson: un altro mondo rispetto al fusore
    assert v.lawson_distance_orders < 2.5


def test_iter_like_machine_exceeds_breakeven():
    """Con i parametri di taglia ITER il modello 0D deve dare Q > 1:
    è il comportamento che lo scaling IPB98 è stato costruito per predire."""
    cfg = _config(
        geometry=_geometry(
            major_radius_m=6.2,
            minor_radius_m=2.0,
            elongation=1.7,
            toroidal_field_t=5.3,
            plasma_current_ma=15.0,
        ),
        physics=TokamakPhysicsConfig(density_1e19_m3=10.0, aux_heating_mw=50.0),
        max_steps=4000,
        dt=0.02,
    )
    *_, final = Tokamak0DEngine(cfg).run()
    d = final.diagnostics
    assert d.q_factor > 1.0
    assert final.physics_verdict.lawson_distance_orders < 0.5
    assert d.tau_e_s > 1.0  # ITER: tempi di confinamento di secondi


def test_temperature_reaches_steady_state():
    engine = Tokamak0DEngine(_config(max_steps=4000, snapshot_interval=1000))
    temps = [s.diagnostics.t_kev for s in engine.run()]
    # verso la fine la temperatura non cambia quasi più
    assert abs(temps[-1] - temps[-2]) < 0.05 * temps[-1]


def test_huge_dt_gives_unreliable_verdict():
    cfg = _config(max_steps=50, dt=1.0)  # dt >> tau_E
    *_, final = Tokamak0DEngine(cfg).run()
    v = final.physics_verdict
    assert v.numerical_reliability is NumericalReliability.UNRELIABLE
    assert v.fusion_rate_per_s is None


def test_stop_condition_on_q_factor():
    cfg = _config(
        max_steps=5000,
        snapshot_interval=100,
        stop_conditions=(StopCondition(metric="q_factor", op=">", threshold=0.05),),
    )
    *_, final = Tokamak0DEngine(cfg).run()
    assert final.meta.step < 5000


def test_unknown_stop_metric_rejected():
    cfg = _config(
        stop_conditions=(StopCondition(metric="grid_loss_w", op=">", threshold=1),)
    )
    with pytest.raises(ValueError, match="Metrica di stop"):
        Tokamak0DEngine(cfg)


# --------------------------------------------------------- orchestratore


def test_orchestrator_tokamak_domain_lifecycle():
    orch = Orchestrator()
    orch.set_domain("tokamak")
    assert orch.judgeable() == (True, "")

    from fusor_sim.contracts.chat_intent import ChatAction, ChatIntent

    res = orch.apply_intent(
        ChatIntent(
            action=ChatAction.SET, target="tokamak_geometry.major_radius_m", value=3.0
        )
    )
    assert res.accepted

    orch.prepare(max_steps=1500, snapshot_interval=500)
    assert orch.run_config.geometry.major_radius_m == 3.0
    assert orch.run_config.solver_selection.engine_id == "tokamak_0d_v1"
    orch.start()
    while orch.state is OrchestratorState.RUN:
        orch.advance()
    assert orch.last_state.domain == "tokamak"
    assert orch.last_state.physics_verdict.honest_summary

    # l'anteprima di campo elettrostatico è del fusore
    with pytest.raises(StateError, match="dominio fusore"):
        orch.field_preview()

    orch.set_domain("fusor")
    assert orch.domain == "fusor"


def test_domain_switch_blocked_during_run():
    orch = Orchestrator()
    orch.prepare(n_particles=1000, max_steps=400, snapshot_interval=200, probe=False)
    orch.start()
    with pytest.raises(StateError, match="durante RUN"):
        orch.set_domain("tokamak")
    while orch.state is OrchestratorState.RUN:
        orch.advance()
