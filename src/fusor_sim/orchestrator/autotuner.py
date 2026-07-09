"""Auto-tuner: sceglie i parametri numerici (proprietario del gruppo
`numerics` della RunConfig). Gira nello stato CONFIG.

Obiettivo: massima velocità sotto vincolo di stabilità. Due fasi:
1. regole a priori — risoluzione che descriva la geometria del catodo,
   passo temporale da CFL particellare sulla velocità massima di caduta;
2. verifica empirica — un probe run corto; se la salute numerica non
   soddisfa le soglie, il passo viene dimezzato e si riprova.

Se nemmeno l'ultimo tentativo è stabile si fallisce rumorosamente:
l'auto-tuner non consegna mai numeri che sa essere inaffidabili.
"""

import numpy as np

from fusor_sim.catalog import get_pusher_class
from fusor_sim.contracts.run_config import (
    GeometryConfig,
    NumericsConfig,
    PhysicsConfig,
    RunConfig,
    RunControl,
    SolverSelection,
)
from fusor_sim.contracts.sim_state import Health
from fusor_sim.engine.particles import M_D, Q_E

_CFL_TARGET = 0.1
_CELLS_BELOW_CATHODE = 20
_PROBE_ENERGY_ERR_MAX = 0.01
_MAX_ATTEMPTS = 3


def tune_numerics(
    geometry: GeometryConfig,
    physics: PhysicsConfig,
    solver_selection: SolverSelection,
    *,
    n_particles: int = 20_000,
    probe: bool = True,
    probe_steps: int = 400,
    seed: int = 0,
) -> NumericsConfig:
    # risoluzione: il catodo deve essere descritto da abbastanza celle
    h_target = geometry.cathode_radius_m / _CELLS_BELOW_CATHODE
    n_nodes = int(np.clip(round(geometry.anode_radius_m / h_target) + 1, 16, 1024))
    h = geometry.anode_radius_m / (n_nodes - 1)

    # CFL particellare sulla velocità di caduta massima q*|V|
    v_max = np.sqrt(2.0 * Q_E * abs(physics.cathode_voltage_v) / M_D)
    dt = min(_CFL_TARGET * h / v_max, 1e-6)

    last_health: Health | None = None
    for _ in range(_MAX_ATTEMPTS):
        numerics = NumericsConfig(
            grid_resolution=n_nodes, n_particles=n_particles, dt_s=dt
        )
        if not probe:
            return numerics
        last_health = _probe_health(
            geometry, physics, solver_selection, numerics, probe_steps, seed
        )
        if (
            last_health.energy_conservation_error < _PROBE_ENERGY_ERR_MAX
            and last_health.cfl_number <= 1.0
        ):
            return numerics
        dt /= 2.0

    raise RuntimeError(
        "Auto-tuner: impossibile stabilizzare la simulazione entro "
        f"{_MAX_ATTEMPTS} tentativi (ultimo probe: errore energia "
        f"{last_health.energy_conservation_error:.2e}, CFL {last_health.cfl_number:.2g}). "
        "Configurazione probabilmente estrema: rivedere geometria o tensione."
    )


def _probe_health(
    geometry: GeometryConfig,
    physics: PhysicsConfig,
    solver_selection: SolverSelection,
    numerics: NumericsConfig,
    probe_steps: int,
    seed: int,
) -> Health:
    config = RunConfig(
        geometry=geometry,
        physics=physics,
        numerics=numerics,
        solver_selection=solver_selection,
        run_control=RunControl(
            max_steps=probe_steps,
            snapshot_interval=probe_steps,
            checkpoint_interval=probe_steps,
        ),
    )
    engine = get_pusher_class(solver_selection.pusher_id)(config, seed=seed)
    *_, final = engine.run()
    return final.health
