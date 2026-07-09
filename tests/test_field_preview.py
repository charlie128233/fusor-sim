"""Test di offset del catodo, solver 3D e anteprima di campo:
la strada 2 (non giudicabile, dichiarato) e la strada 3 (solo campo)."""

import numpy as np
import pytest
from pydantic import ValidationError

from fusor_sim.contracts.field_preview import FieldPreview
from fusor_sim.contracts.physics_verdict import (
    LossBreakdown,
    NumericalReliability,
    PhysicsVerdict,
)
from fusor_sim.contracts.run_config import GeometryConfig
from fusor_sim.orchestrator import Orchestrator, OrchestratorState, StateError
from fusor_sim.orchestrator.router import select_solvers
from fusor_sim.solvers.poisson_cartesian3d import PoissonCartesian3DSolver

R_CATHODE = 0.05
R_ANODE = 0.15
V_CATHODE = -40_000.0


def _geometry(**overrides) -> GeometryConfig:
    base = dict(
        chamber_radius_m=0.25,
        anode_radius_m=R_ANODE,
        cathode_radius_m=R_CATHODE,
        grid_transparency=0.95,
    )
    base.update(overrides)
    return GeometryConfig(**base)


# ----------------------------------------------------- contratti: offset


def test_offset_defaults_to_concentric():
    geo = _geometry()
    assert geo.is_concentric
    assert geo.cathode_offset_magnitude_m == 0.0


def test_offset_geometry_is_valid_but_not_concentric():
    geo = _geometry(cathode_offset_x_m=0.03)
    assert not geo.is_concentric
    assert geo.cathode_offset_magnitude_m == pytest.approx(0.03)


def test_offset_cannot_push_cathode_outside_anode():
    with pytest.raises(ValidationError, match="uscirebbe dall'anodo"):
        _geometry(cathode_offset_x_m=0.11)  # 0.11 + 0.05 > 0.15


# --------------------------------------------- contratti: scope field_only


def _zero_losses():
    return LossBreakdown(grid_w=0, radiation_w=0, conduction_w=0, escape_w=0)


def test_field_only_verdict_cannot_report_fusion_numbers():
    with pytest.raises(ValidationError, match="solo campo"):
        PhysicsVerdict(
            scope="field_only",
            numerical_reliability=NumericalReliability.RELIABLE,
            produces_fusion=True,  # vietato in un'anteprima di campo
            fusion_rate_per_s=1e5,
            fusion_power_w=1e-7,
            input_power_w=0.0,
            net_energy_balance_w=-10.0,
            loss_breakdown=_zero_losses(),
            lawson_distance_orders=10.0,
            honest_summary="x",
        )


def test_field_preview_requires_field_only_verdict():
    full_verdict = PhysicsVerdict(
        scope="full",
        numerical_reliability=NumericalReliability.UNRELIABLE,
        produces_fusion=None,
        fusion_rate_per_s=None,
        fusion_power_w=None,
        input_power_w=0.0,
        net_energy_balance_w=None,
        loss_breakdown=_zero_losses(),
        lawson_distance_orders=None,
        honest_summary="x",
    )
    with pytest.raises(ValidationError, match="field_only"):
        FieldPreview(
            grid_extent_m=R_ANODE,
            n_nodes=16,
            slice_z0_v=np.zeros((16, 16)),
            slice_y0_v=np.zeros((16, 16)),
            cathode_offset_m=(0, 0, 0),
            converged=True,
            residual_rel=1e-9,
            physics_verdict=full_verdict,
        )


# ------------------------------------------------------------- solver 3D


def test_3d_concentric_matches_radial_analytic():
    """Caso concentrico: il 3D deve riprodurre il profilo 1/r del radiale."""
    field = PoissonCartesian3DSolver().solve(_geometry(), V_CATHODE, n_nodes=64)
    assert field.converged

    n = len(field.axis_m)
    denom = 1.0 / R_CATHODE - 1.0 / R_ANODE
    mid = n // 2
    # campiona lungo l'asse +x a metà intercapedine
    r_target = (R_CATHODE + R_ANODE) / 2
    i = int(np.argmin(np.abs(field.axis_m - r_target)))
    numeric = field.potential_v[i, mid, mid]
    r_i = abs(field.axis_m[i])
    analytic = V_CATHODE * (1.0 / r_i - 1.0 / R_ANODE) / denom
    assert numeric == pytest.approx(analytic, rel=0.08)  # sfere a gradini: O(h)

    # dentro il catodo: gabbia di Faraday
    assert field.potential_v[mid, mid, mid] == pytest.approx(V_CATHODE)
    # fuori dall'anodo: massa
    assert field.potential_v[0, 0, 0] == 0.0


def test_3d_offset_breaks_symmetry_honestly():
    """Catodo spostato in +x: il potenziale a metà strada deve essere più
    profondo dal lato verso cui si è spostato."""
    field = PoissonCartesian3DSolver().solve(
        _geometry(cathode_offset_x_m=0.04), V_CATHODE, n_nodes=64
    )
    assert field.converged
    n = len(field.axis_m)
    mid = n // 2
    r_probe = 0.11
    ip = int(np.argmin(np.abs(field.axis_m - r_probe)))
    im = int(np.argmin(np.abs(field.axis_m + r_probe)))
    phi_plus = field.potential_v[ip, mid, mid]  # lato vicino al catodo
    phi_minus = field.potential_v[im, mid, mid]  # lato lontano
    assert phi_plus < phi_minus < 0.0


# --------------------------------------------------- router e orchestratore


def test_router_refuses_offset_geometry_with_explanation():
    with pytest.raises(ValueError, match="non concentrica"):
        select_solvers(_geometry(cathode_offset_x_m=0.03))


def test_orchestrator_judgeable_flag():
    orch = Orchestrator()
    ok, reason = orch.judgeable()
    assert ok and reason == ""
    orch.geometry = _geometry(cathode_offset_x_m=0.03)
    ok, reason = orch.judgeable()
    assert not ok
    assert "anteprima" in reason


def test_prepare_blocked_for_offset_geometry():
    orch = Orchestrator()
    orch.geometry = _geometry(cathode_offset_x_m=0.03)
    with pytest.raises(ValueError, match="non concentrica"):
        orch.prepare(n_particles=1000, max_steps=400, snapshot_interval=200, probe=False)


def test_orchestrator_field_preview_offset():
    orch = Orchestrator()
    orch.geometry = _geometry(cathode_offset_x_m=0.03)
    preview = orch.field_preview(n_nodes=48)
    v = preview.physics_verdict
    assert v.scope == "field_only"
    assert v.produces_fusion is None
    assert "NON giudicabile" in v.honest_summary
    assert preview.slice_z0_v.shape == (48, 48)
    assert preview.cathode_offset_m == (0.03, 0.0, 0.0)


def test_orchestrator_field_preview_concentric_mentions_run():
    orch = Orchestrator()
    preview = orch.field_preview(n_nodes=48)
    assert "avvia un run" in preview.physics_verdict.honest_summary


def test_field_preview_forbidden_during_run():
    orch = Orchestrator()
    orch.prepare(n_particles=1000, max_steps=400, snapshot_interval=200, probe=False)
    orch.start()
    with pytest.raises(StateError, match="durante RUN"):
        orch.field_preview()
    while orch.state is OrchestratorState.RUN:
        orch.advance()
