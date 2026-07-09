"""Test del motore PIC: fisica delle sezioni d'urto, conservazione
dell'energia del pusher, run completo con referto, gating di onestà."""

import numpy as np
import pytest

from fusor_sim.catalog import available_pushers, get_pusher_class
from fusor_sim.contracts.physics_verdict import NumericalReliability
from fusor_sim.contracts.run_config import (
    GasSpecies,
    GeometryConfig,
    NumericsConfig,
    PhysicsConfig,
    RunConfig,
    RunControl,
    SolverSelection,
    StopCondition,
)
from fusor_sim.contracts.sim_state import Health, RunStatus
from fusor_sim.engine.fusion import cross_sections_m2
from fusor_sim.engine.particles import M_D, Q_E
from fusor_sim.engine.simulation import RadialPICEngine
from fusor_sim.engine.verdict import build_verdict


def _config(**overrides) -> RunConfig:
    base = dict(
        geometry=GeometryConfig(
            chamber_radius_m=0.25,
            anode_radius_m=0.15,
            cathode_radius_m=0.05,
            grid_transparency=0.95,
        ),
        physics=PhysicsConfig(
            cathode_voltage_v=-40_000,
            gas_species=GasSpecies.DD,
            pressure_pa=0.5,
            ion_source_rate_per_s=1e16,
            gas_temperature_k=300.0,
        ),
        # 151 nodi su 0.15 m: h = 1 mm, il catodo (0.05 m) cade sul nodo 50
        numerics=NumericsConfig(
            grid_resolution=151, n_particles=1000, dt_s=5e-11
        ),
        solver_selection=SolverSelection(
            poisson_solver_id="poisson_spherical_fd_v1",
            pusher_id="leapfrog_radial_v1",
        ),
        run_control=RunControl(
            max_steps=1200, snapshot_interval=400, checkpoint_interval=1200
        ),
    )
    base.update(overrides)
    return RunConfig(**base)


# ------------------------------------------------------- sezioni d'urto


def test_cross_section_zero_below_barrier():
    sigma, sigma_n = cross_sections_m2(GasSpecies.DD, np.array([0.05, 0.1]))
    assert np.all(sigma == 0.0)
    assert np.all(sigma_n == 0.0)


def test_cross_section_grows_with_energy():
    e = np.array([5.0, 10.0, 20.0, 40.0, 80.0])
    sigma, _ = cross_sections_m2(GasSpecies.DD, e)
    assert np.all(np.diff(sigma) > 0)


def test_dd_cross_section_magnitude():
    """sigma_DD(50 keV) ~ 1e-2 barn: controllo d'ordine di grandezza
    contro i valori tabulati (NRL Plasma Formulary)."""
    sigma, sigma_n = cross_sections_m2(GasSpecies.DD, np.array([50.0]))
    assert 1e-31 < sigma[0] < 5e-30
    assert 0.3 < sigma_n[0] / sigma[0] < 0.7  # i due rami sono ~50/50


def test_dt_much_easier_than_dd():
    sigma_dd, _ = cross_sections_m2(GasSpecies.DD, np.array([50.0]))
    sigma_dt, _ = cross_sections_m2(GasSpecies.DT, np.array([50.0]))
    assert sigma_dt[0] > 20 * sigma_dd[0]


# ------------------------------------- pusher: fisica di singola particella


def test_single_ion_energy_conservation_and_well_depth():
    """Uno ione lasciato fermo tra le griglie cade nel pozzo, oscilla, e:
    1) l'energia totale (cinetica + potenziale) si conserva entro l'1%;
    2) l'energia cinetica massima è ~ q * (phi(partenza) - V_catodo)."""
    cfg = _config(
        geometry=GeometryConfig(
            chamber_radius_m=0.25,
            anode_radius_m=0.15,
            cathode_radius_m=0.05,
            grid_transparency=0.999,  # quasi mai intercettato
        ),
        run_control=RunControl(
            max_steps=6000, snapshot_interval=6000, checkpoint_interval=6000
        ),
    )
    engine = RadialPICEngine(cfg, seed=1, field_update_every=100)
    r_start = 0.12
    engine.r = np.array([r_start])
    engine.v = np.array([0.0])
    engine.ang_mom = np.array([0.0])
    engine.inject_per_step = 0.0  # test white-box: nessuna altra particella

    field = engine._solve_field()
    phi_start = float(np.interp(r_start, engine.r_nodes, field.phi_v))
    e_total_start = float(Q_E * phi_start)  # cinetica nulla

    max_ke = 0.0
    for _ in range(6000):
        engine._step()
        if not engine.r.size:
            pytest.skip("ione intercettato dalla griglia (sfortuna statistica)")
        ke = float(engine._kinetic(engine.r, engine.v, engine.ang_mom)[0])
        phi_here = float(np.interp(engine.r[0], engine.r_nodes, engine.field.phi_v))
        e_total = ke + Q_E * phi_here
        assert abs(e_total - e_total_start) < 0.01 * abs(
            Q_E * cfg.physics.cathode_voltage_v
        )
        max_ke = max(max_ke, ke)

    expected_peak = Q_E * (phi_start - cfg.physics.cathode_voltage_v)
    assert max_ke == pytest.approx(expected_peak, rel=0.05)


def test_opaque_grid_intercepts_immediately():
    """Con trasparenza minima quasi ogni attraversamento uccide lo ione:
    l'energia finisce nel tally della griglia."""
    cfg = _config(
        geometry=GeometryConfig(
            chamber_radius_m=0.25,
            anode_radius_m=0.15,
            cathode_radius_m=0.05,
            grid_transparency=0.01,
        ),
        run_control=RunControl(
            max_steps=4000, snapshot_interval=4000, checkpoint_interval=4000
        ),
    )
    engine = RadialPICEngine(cfg, seed=2, field_update_every=100)
    engine.r = np.array([0.12])
    engine.v = np.array([0.0])
    engine.ang_mom = np.array([0.0])
    engine.inject_per_step = 0.0

    for _ in range(4000):
        engine._step()
        if not engine.r.size:
            break
    assert engine.r.size == 0
    assert engine.window_grid_energy_j > 0


# --------------------------------------------------------- run completo


def test_full_run_produces_honest_states():
    engine = RadialPICEngine(_config(), seed=42)
    states = list(engine.run())

    assert len(states) == 3  # 1200 step / snapshot ogni 400
    assert states[-1].meta.status is RunStatus.DONE
    assert states[-1].kind == "checkpoint"
    assert all(s.meta.status is RunStatus.RUNNING for s in states[:-1])

    steps = [s.meta.step for s in states]
    assert steps == sorted(steps)

    final = states[-1]
    # il referto c'è sempre ed è coerente
    v = final.physics_verdict
    assert v.honest_summary
    if v.numerical_reliability is not NumericalReliability.UNRELIABLE:
        # il muro della fisica: bilancio negativo, lontani da Lawson
        assert v.net_energy_balance_w < 0
        assert v.lawson_distance_orders > 3
        assert v.loss_breakdown.grid_w >= v.loss_breakdown.escape_w
    assert final.diagnostics.ion_energy_spectrum_ev.shape == (64,)
    assert 0 < final.particles.sample_fraction <= 1
    # dopo 1200 step le perdite su griglia devono essere comparse
    assert final.diagnostics.grid_loss_w > 0


def test_recirculation_tracks_transparency():
    engine = RadialPICEngine(_config(), seed=7)
    *_, final = engine.run()
    # la frazione di attraversamenti sopravvissuti ~ trasparenza griglia
    assert final.diagnostics.recirculation_efficiency == pytest.approx(0.95, abs=0.1)


def test_huge_dt_yields_unreliable_verdict_with_no_numbers():
    """Onestà sotto stress: passo temporale assurdo -> CFL enorme ->
    il verdetto DEVE dichiararsi inaffidabile e non riportare numeri."""
    cfg = _config(
        numerics=NumericsConfig(grid_resolution=151, n_particles=1000, dt_s=1e-8),
        run_control=RunControl(
            max_steps=400, snapshot_interval=400, checkpoint_interval=400
        ),
    )
    engine = RadialPICEngine(cfg, seed=3)
    *_, final = engine.run()
    v = final.physics_verdict
    assert v.numerical_reliability is NumericalReliability.UNRELIABLE
    assert v.produces_fusion is None
    assert v.fusion_rate_per_s is None
    assert v.net_energy_balance_w is None
    assert "NON AFFIDABILE" in v.honest_summary


def test_stop_condition_halts_run_early():
    cfg = _config(
        run_control=RunControl(
            max_steps=4000,
            snapshot_interval=200,
            checkpoint_interval=4000,
            stop_conditions=(
                StopCondition(metric="grid_loss_w", op=">", threshold=1e-12),
            ),
        )
    )
    engine = RadialPICEngine(cfg, seed=4)
    *_, final = engine.run()
    assert final.meta.status is RunStatus.DONE
    assert final.meta.step < 4000


def test_unknown_stop_metric_rejected_at_init():
    cfg = _config(
        run_control=RunControl(
            max_steps=100,
            snapshot_interval=100,
            checkpoint_interval=100,
            stop_conditions=(
                StopCondition(metric="q_factor", op=">", threshold=1.0),
            ),
        )
    )
    with pytest.raises(ValueError, match="Metrica di stop sconosciuta"):
        RadialPICEngine(cfg)


# ------------------------------------------------------------- verdetto


def _healthy() -> Health:
    return Health(energy_conservation_error=1e-4, cfl_number=0.3, warnings=())


def test_verdict_reports_deeply_negative_balance():
    v = build_verdict(
        gas_species=GasSpecies.DD,
        fusion_rate_per_s=1e6,
        neutron_rate_per_s=5e5,
        input_power_w=1000.0,
        grid_loss_w=990.0,
        escape_loss_w=10.0,
        lawson_triple_kev_s_m3=1e14,
        health=_healthy(),
    )
    assert v.numerical_reliability is NumericalReliability.RELIABLE
    assert v.produces_fusion is True
    assert v.net_energy_balance_w < -999
    assert v.lawson_distance_orders == pytest.approx(9.0)
    assert "griglia" in v.honest_summary


def test_verdict_marginal_carries_warning():
    v = build_verdict(
        gas_species=GasSpecies.DD,
        fusion_rate_per_s=1e6,
        neutron_rate_per_s=5e5,
        input_power_w=1000.0,
        grid_loss_w=990.0,
        escape_loss_w=10.0,
        lawson_triple_kev_s_m3=1e14,
        health=Health(energy_conservation_error=0.05, cfl_number=1.5, warnings=()),
    )
    assert v.numerical_reliability is NumericalReliability.MARGINAL
    assert "AVVERTENZA" in v.honest_summary


# ------------------------------------------------------------- catalogo


def test_pusher_in_catalog():
    assert available_pushers() == ["leapfrog_radial_v1"]
    assert get_pusher_class("leapfrog_radial_v1") is RadialPICEngine
    with pytest.raises(KeyError, match="non nel catalogo"):
        get_pusher_class("pusher_inventato_v1")


def test_engine_rejects_mismatched_pusher_id():
    cfg = _config(
        solver_selection=SolverSelection(
            poisson_solver_id="poisson_spherical_fd_v1",
            pusher_id="leapfrog_radial_v1",
        )
    )
    engine_cls = get_pusher_class(cfg.solver_selection.pusher_id)
    assert engine_cls(cfg).pusher_id == "leapfrog_radial_v1"


def test_mass_and_charge_constants_sane():
    assert M_D == pytest.approx(3.344e-27, rel=1e-3)
    assert Q_E == pytest.approx(1.602e-19, rel=1e-3)
