"""Test dei contratti dati: verificano che le regole di onestà siano
strutturali (violarle = ValidationError), non convenzioni."""

import numpy as np
import pytest
from pydantic import ValidationError

from fusor_sim.contracts import (
    ChatAction,
    ChatIntent,
    Diagnostics,
    FieldSnapshot,
    GeometryConfig,
    Health,
    LossBreakdown,
    NumericalReliability,
    NumericsConfig,
    Owner,
    owner_of,
    ParticleSample,
    PhysicsVerdict,
    RunStatus,
    SimMeta,
    SimState,
)
from fusor_sim.contracts.run_config import example_run_config

# ---------------------------------------------------------------- RunConfig


def test_example_run_config_is_valid():
    cfg = example_run_config()
    assert cfg.geometry.cathode_radius_m < cfg.geometry.anode_radius_m


def test_run_config_is_frozen():
    cfg = example_run_config()
    with pytest.raises(ValidationError):
        cfg.physics.pressure_pa = 1.0
    with pytest.raises(ValidationError):
        cfg.geometry = cfg.geometry


def test_unrealizable_geometry_rejected():
    with pytest.raises(ValidationError, match="non realizzabile"):
        GeometryConfig(
            chamber_radius_m=0.25,
            anode_radius_m=0.05,  # anodo dentro il catodo: impossibile
            cathode_radius_m=0.15,
            grid_transparency=0.95,
        )


def test_positive_cathode_voltage_rejected():
    cfg = example_run_config()
    with pytest.raises(ValidationError):
        type(cfg.physics)(**{**cfg.physics.model_dump(), "cathode_voltage_v": 40_000})


def test_cuda_block_size_must_be_warp_multiple():
    with pytest.raises(ValidationError, match="multiplo di 32"):
        NumericsConfig(grid_resolution=64, n_particles=10_000, dt_s=1e-9, cuda_block_size=100)


# ---------------------------------------------------------------- ownership


def test_ownership_map():
    assert owner_of("physics.pressure_pa") is Owner.USER
    assert owner_of("geometry.cathode_radius_m") is Owner.USER
    assert owner_of("numerics.dt_s") is Owner.AUTO_TUNER
    assert owner_of("solver_selection.pusher_id") is Owner.ROUTER
    assert owner_of("run_control.max_steps") is Owner.ORCHESTRATOR


def test_ownership_rejects_unknown_paths():
    with pytest.raises(ValueError, match="Gruppo sconosciuto"):
        owner_of("magnetics.coil_current")
    with pytest.raises(ValueError, match="Campo sconosciuto"):
        owner_of("physics.warp_drive")


# ---------------------------------------------------------------- ChatIntent


def test_chat_can_set_user_owned_field():
    intent = ChatIntent(action=ChatAction.SET, target="physics.pressure_pa", value=0.8)
    assert intent.value == 0.8


def test_chat_cannot_touch_autotuner_fields():
    with pytest.raises(ValidationError, match="auto_tuner"):
        ChatIntent(action=ChatAction.SET, target="numerics.dt_s", value=1e-12)


def test_chat_cannot_touch_router_fields():
    with pytest.raises(ValidationError, match="router"):
        ChatIntent(action=ChatAction.SCALE, target="solver_selection.pusher_id", value=2)


def test_chat_set_on_invented_path_rejected():
    with pytest.raises(ValidationError, match="sconosciut"):
        ChatIntent(action=ChatAction.SET, target="physics.magic_field", value=1)


def test_scale_requires_numeric_factor():
    with pytest.raises(ValidationError, match="fattore numerico"):
        ChatIntent(action=ChatAction.SCALE, target="physics.pressure_pa", value="double")


def test_query_needs_no_target():
    ChatIntent(action=ChatAction.QUERY, value=None, target=None)


# ---------------------------------------------------------- PhysicsVerdict


def _losses():
    return LossBreakdown(grid_w=950.0, radiation_w=30.0, conduction_w=15.0, escape_w=5.0)


def _reliable_verdict(**overrides):
    base = dict(
        numerical_reliability=NumericalReliability.RELIABLE,
        produces_fusion=True,
        fusion_rate_per_s=1e6,
        fusion_power_w=5.8e-7,
        input_power_w=1000.0,
        net_energy_balance_w=-999.999,
        loss_breakdown=_losses(),
        lawson_distance_orders=8.5,
        honest_summary=(
            "Il fusore produce fusione (1e6 reazioni/s) ma consuma ~1 kW per "
            "generare meno di un microwatt: bilancio profondamente negativo, "
            "a 8.5 ordini di grandezza dalla soglia di Lawson."
        ),
    )
    base.update(overrides)
    return PhysicsVerdict(**base)


def test_honest_verdict_builds():
    v = _reliable_verdict()
    assert v.net_energy_balance_w < 0
    assert v.loss_breakdown.total_w == pytest.approx(1000.0)


def test_produces_fusion_cannot_contradict_rate():
    with pytest.raises(ValidationError, match="Incoerenza"):
        _reliable_verdict(produces_fusion=False)  # con tasso 1e6/s
    with pytest.raises(ValidationError, match="Incoerenza"):
        _reliable_verdict(produces_fusion=True, fusion_rate_per_s=0.0)


def test_unreliable_result_must_not_report_numbers():
    with pytest.raises(ValidationError, match="inaffidabile"):
        _reliable_verdict(numerical_reliability=NumericalReliability.UNRELIABLE)


def test_unreliable_verdict_with_nulled_numbers_is_valid():
    v = PhysicsVerdict(
        numerical_reliability=NumericalReliability.UNRELIABLE,
        produces_fusion=None,
        fusion_rate_per_s=None,
        fusion_power_w=None,
        input_power_w=1000.0,
        net_energy_balance_w=None,
        loss_breakdown=_losses(),
        lawson_distance_orders=None,
        honest_summary=(
            "La conservazione dell'energia è violata oltre soglia: il risultato "
            "non è affidabile e nessun numero di fusione viene riportato. "
            "Riduci il passo temporale e riprova."
        ),
    )
    assert v.produces_fusion is None


def test_reliable_verdict_cannot_omit_numbers():
    with pytest.raises(ValidationError, match="incompleto"):
        _reliable_verdict(lawson_distance_orders=None)


# ---------------------------------------------------------------- SimState


def _sim_state_kwargs():
    n = 100
    res = 32
    return dict(
        kind="snapshot",
        meta=SimMeta(step=500, sim_time_s=5e-7, status=RunStatus.RUNNING, wall_clock_s=12.3),
        fields=FieldSnapshot(
            potential_v=np.zeros((res, res)),
            e_field_v_per_m=np.zeros((res, res, 2)),
            charge_density_c_per_m3=np.zeros((res, res)),
        ),
        particles=ParticleSample(
            positions_m=np.zeros((n, 3)),
            velocities_m_per_s=np.zeros((n, 3)),
            energies_ev=np.zeros(n),
            sample_fraction=0.001,
        ),
        diagnostics=Diagnostics(
            fusion_rate_per_s=1e6,
            neutron_rate_per_s=5e5,
            ion_energy_spectrum_ev=np.zeros(64),
            grid_loss_w=950.0,
            recirculation_efficiency=0.7,
            power_balance_w=-999.999,
        ),
        health=Health(energy_conservation_error=1e-5, cfl_number=0.4, warnings=()),
        physics_verdict=_reliable_verdict(),
    )


def test_sim_state_builds_with_verdict():
    state = SimState(**_sim_state_kwargs())
    assert state.physics_verdict.honest_summary


def test_sim_state_without_verdict_is_impossible():
    kwargs = _sim_state_kwargs()
    del kwargs["physics_verdict"]
    with pytest.raises(ValidationError):
        SimState(**kwargs)


def test_field_shapes_must_be_consistent():
    with pytest.raises(ValidationError, match="Shape incoerenti"):
        FieldSnapshot(
            potential_v=np.zeros((32, 32)),
            e_field_v_per_m=np.zeros((32, 32, 2)),
            charge_density_c_per_m3=np.zeros((16, 16)),
        )


def test_particle_arrays_must_align():
    with pytest.raises(ValidationError, match="incoerente"):
        ParticleSample(
            positions_m=np.zeros((100, 3)),
            velocities_m_per_s=np.zeros((99, 3)),
            energies_ev=np.zeros(100),
            sample_fraction=0.001,
        )
