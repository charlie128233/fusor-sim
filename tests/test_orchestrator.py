"""Test di orchestratore, router e auto-tuner: il gating strutturale
della chat e il ciclo di vita IDLE -> CONFIG -> RUN -> PAUSED -> DONE."""

import pytest

from fusor_sim.contracts.chat_intent import ChatAction, ChatIntent
from fusor_sim.contracts.physics_verdict import NumericalReliability
from fusor_sim.contracts.run_config import example_run_config
from fusor_sim.engine.particles import M_D, Q_E
from fusor_sim.orchestrator import (
    Orchestrator,
    OrchestratorState,
    StateError,
    select_solvers,
    tune_numerics,
)


def _prepare_kwargs(**overrides):
    """Config piccola e senza probe per test veloci del ciclo di vita."""
    base = dict(
        n_particles=1000, max_steps=600, snapshot_interval=200, probe=False
    )
    base.update(overrides)
    return base


# --------------------------------------------------------------- router


def test_router_selects_validated_solvers():
    sel = select_solvers(example_run_config().geometry)
    assert sel.poisson_solver_id == "poisson_spherical_fd_v1"
    assert sel.pusher_id == "leapfrog_radial_v1"


# ----------------------------------------------------------- auto-tuner


def test_autotuner_respects_cfl_bound():
    cfg = example_run_config()
    sel = select_solvers(cfg.geometry)
    num = tune_numerics(cfg.geometry, cfg.physics, sel, probe=False)
    h = cfg.geometry.anode_radius_m / (num.grid_resolution - 1)
    v_max = (2.0 * Q_E * abs(cfg.physics.cathode_voltage_v) / M_D) ** 0.5
    assert num.dt_s * v_max / h <= 0.11
    # il catodo deve avere abbastanza celle sotto di sé
    assert cfg.geometry.cathode_radius_m / h >= 15


def test_autotuner_probe_delivers_stable_numerics():
    """Il probe empirico deve consegnare numeri che il motore giudica sani."""
    cfg = example_run_config()
    sel = select_solvers(cfg.geometry)
    num = tune_numerics(
        cfg.geometry, cfg.physics, sel, n_particles=1000, probe=True, probe_steps=300
    )
    assert num.dt_s > 0  # se il probe non stabilizza, tune_numerics solleva


# --------------------------------------------------- ciclo di vita base


def test_full_lifecycle():
    orch = Orchestrator()
    assert orch.state is OrchestratorState.IDLE

    # in IDLE la chat propone e l'orchestratore valida
    res = orch.apply_intent(
        ChatIntent(action=ChatAction.SET, target="physics.cathode_voltage_v", value=-30_000)
    )
    assert res.accepted

    orch.prepare(**_prepare_kwargs())
    assert orch.state is OrchestratorState.CONFIG
    assert orch.run_config.physics.cathode_voltage_v == -30_000
    # i tre gruppi hanno tre proprietari: numerics dal tuner, solver dal router
    assert orch.run_config.numerics.dt_s > 0
    assert orch.run_config.solver_selection.pusher_id == "leapfrog_radial_v1"

    orch.start()
    assert orch.state is OrchestratorState.RUN

    pulled = orch.advance()
    assert len(pulled) == 1
    assert pulled[0].physics_verdict.honest_summary  # referto sempre presente

    orch.pause()
    assert orch.state is OrchestratorState.PAUSED
    # in PAUSED la chat torna a poter parlare
    res = orch.apply_intent(ChatIntent(action=ChatAction.QUERY, target="physics.pressure_pa"))
    assert res.accepted

    orch.resume()
    remaining = orch.advance(snapshots=10)
    assert orch.state is OrchestratorState.DONE
    assert remaining[-1].meta.status.value == "done"
    assert orch.last_state.physics_verdict is not None


def test_chat_is_structurally_gated_during_run():
    orch = Orchestrator()
    orch.prepare(**_prepare_kwargs())
    intent = ChatIntent(action=ChatAction.SET, target="physics.pressure_pa", value=1.0)

    with pytest.raises(StateError, match="IDLE o PAUSED"):
        orch.apply_intent(intent)  # CONFIG: no
    orch.start()
    with pytest.raises(StateError, match="IDLE o PAUSED"):
        orch.apply_intent(intent)  # RUN: no
    with pytest.raises(StateError, match="RunConfig durante RUN"):
        orch.prepare(**_prepare_kwargs())  # nessuna nuova config in RUN


def test_advance_requires_run_state():
    orch = Orchestrator()
    with pytest.raises(StateError, match="advance"):
        orch.advance()


def test_prepare_from_paused_discards_run():
    orch = Orchestrator()
    orch.prepare(**_prepare_kwargs())
    orch.start()
    orch.advance()
    orch.pause()
    orch.apply_intent(
        ChatIntent(action=ChatAction.SET, target="physics.pressure_pa", value=2.0)
    )
    orch.prepare(**_prepare_kwargs())  # riconfigura: il run in pausa muore
    assert orch.state is OrchestratorState.CONFIG
    assert orch.run_config.physics.pressure_pa == 2.0
    assert any("scartato" in h for h in orch.history)


# ------------------------------------------------------ intent e vincoli


def test_physical_validation_rejects_bad_values():
    orch = Orchestrator()
    res = orch.apply_intent(
        ChatIntent(action=ChatAction.SET, target="physics.cathode_voltage_v", value=+40_000)
    )
    assert not res.accepted
    assert "vincoli fisici" in res.message
    # la bozza non è stata toccata
    assert orch.physics.cathode_voltage_v == -40_000


def test_unrealizable_geometry_rejected_with_reason():
    orch = Orchestrator()
    res = orch.apply_intent(
        ChatIntent(action=ChatAction.SET, target="geometry.cathode_radius_m", value=0.2)
    )
    assert not res.accepted  # catodo fuori dall'anodo (0.15 m)


def test_scale_intent():
    orch = Orchestrator()
    res = orch.apply_intent(
        ChatIntent(action=ChatAction.SCALE, target="physics.pressure_pa", value=2.0)
    )
    assert res.accepted
    assert orch.physics.pressure_pa == pytest.approx(1.0)  # 0.5 * 2


def test_constraint_blocks_future_sets():
    """Il caso del documento di visione: l'alimentatore arriva a 30 kV."""
    orch = Orchestrator()
    orch.apply_intent(
        ChatIntent(action=ChatAction.SET, target="physics.cathode_voltage_v", value=-25_000)
    )
    res = orch.apply_intent(
        ChatIntent(
            action=ChatAction.ADD_CONSTRAINT,
            target="physics.cathode_voltage_v",
            value=">= -30000",
            rationale="alimentatore HV-30 del catalogo componenti",
        )
    )
    assert res.accepted

    res = orch.apply_intent(
        ChatIntent(action=ChatAction.SET, target="physics.cathode_voltage_v", value=-80_000)
    )
    assert not res.accepted
    assert "vincolo" in res.message
    assert orch.physics.cathode_voltage_v == -25_000

    res = orch.apply_intent(
        ChatIntent(action=ChatAction.SET, target="physics.cathode_voltage_v", value=-28_000)
    )
    assert res.accepted


def test_constraint_rejected_if_already_violated():
    orch = Orchestrator()  # tensione di default -40 kV
    res = orch.apply_intent(
        ChatIntent(
            action=ChatAction.ADD_CONSTRAINT,
            target="physics.cathode_voltage_v",
            value=">= -30000",
        )
    )
    assert not res.accepted
    assert "viola già" in res.message


def test_query_and_formula_source():
    orch = Orchestrator()
    res = orch.apply_intent(ChatIntent(action=ChatAction.QUERY, target="physics.pressure_pa"))
    assert res.accepted and "0.5" in res.message

    res = orch.apply_intent(ChatIntent(action=ChatAction.QUERY, target="physics.inventato"))
    assert not res.accepted

    res = orch.apply_intent(
        ChatIntent(action=ChatAction.ADD_FORMULA_SOURCE, value="NRL Plasma Formulary 2019")
    )
    assert res.accepted
    assert orch.formula_sources == ["NRL Plasma Formulary 2019"]


def test_history_records_transitions_and_intents():
    orch = Orchestrator()
    orch.apply_intent(
        ChatIntent(action=ChatAction.SET, target="physics.pressure_pa", value=0.8)
    )
    orch.prepare(**_prepare_kwargs())
    assert any("idle -> config" in h for h in orch.history)
    assert any("intent SET physics.pressure_pa: ok" in h for h in orch.history)


# ------------------------------------------- integrazione con il motore


def test_orchestrated_run_produces_honest_verdict():
    """Ciclo completo orchestrato con auto-tuner (probe incluso):
    il verdetto finale deve essere affidabile e fisicamente onesto."""
    orch = Orchestrator()
    orch.prepare(n_particles=1000, max_steps=2000, snapshot_interval=500, probe=True)
    orch.start()
    while orch.state is OrchestratorState.RUN:
        orch.advance()
    v = orch.last_state.physics_verdict
    assert v.numerical_reliability in (
        NumericalReliability.RELIABLE,
        NumericalReliability.MARGINAL,
    )
    assert v.net_energy_balance_w < 0
    assert v.lawson_distance_orders > 3
