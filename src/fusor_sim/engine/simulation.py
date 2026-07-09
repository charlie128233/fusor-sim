"""Loop caldo del PIC radiale sferico.

Ciclo per step: deposizione carica -> solve Poisson -> push leapfrog
(kick-drift-kick) -> bordi (centro, griglia, parete) -> iniezione ->
tally diagnostici. Ogni `snapshot_interval` step emette un SimState
completo di referto.

Fisica del moto: splitting kick-drift-kick. Il kick applica solo il campo
elettrico a v_r; il drift avanza il moto LIBERO in modo analitico esatto
(r(t) = |R0 + V t| con L conservato), quindi il passaggio al pericentro
— la singolarità centrifuga che affligge i codici radiali — è risolto
esattamente, senza forza 1/r^3 discretizzata. Lo scarto misurato tra
variazione di energia cinetica e lavoro del campo È la metrica di
affidabilità del referto.

Contabilità delle perdite:
- griglia: attraversando il raggio del catodo, intercettazione con
  probabilità (1 - trasparenza); l'energia cinetica va al tally griglia;
- parete: uno ione che raggiunge l'anodo è assorbito (tally fuga);
- radiazione/elettroni: NON modellati, dichiarato nel referto.
"""

import time
from collections.abc import Iterator

import numpy as np

from fusor_sim.catalog import get_poisson_solver
from fusor_sim.contracts.run_config import RunConfig, StopCondition
from fusor_sim.contracts.sim_state import (
    Diagnostics,
    FieldSnapshot,
    Health,
    ParticleSample,
    RunStatus,
    SimMeta,
    SimState,
)
from fusor_sim.engine.fusion import ENERGY_PER_FUSION_J, cross_sections_m2
from fusor_sim.engine.particles import (
    K_B,
    M_D,
    Q_E,
    deposit_charge,
    sample_injection,
    shell_volumes,
)
from fusor_sim.engine.verdict import build_verdict
from fusor_sim.solvers.poisson_spherical import RadialPotential

_KEV_J = 1.602176634e-16
_EV_J = 1.602176634e-19
_SPECTRUM_BINS = 64
_VIZ_SAMPLE_MAX = 200
_R_TINY = 1e-12  # m, solo guardia anti-divisione-per-zero (r=0 esatto con L=0)

_OPS = {
    "<": np.less,
    "<=": np.less_equal,
    ">": np.greater,
    ">=": np.greater_equal,
}


class RadialPICEngine:
    """Motore PIC radiale 1D. Id nel catalogo: leapfrog_radial_v1."""

    pusher_id = "leapfrog_radial_v1"

    def __init__(self, config: RunConfig, seed: int = 0, field_update_every: int = 1):
        if config.solver_selection.pusher_id != self.pusher_id:
            raise ValueError(
                f"Questo motore è '{self.pusher_id}', la config chiede "
                f"'{config.solver_selection.pusher_id}'"
            )
        self.config = config
        self.rng = np.random.default_rng(seed)
        self.poisson = get_poisson_solver(config.solver_selection.poisson_solver_id)
        self.field_update_every = field_update_every

        geo, phys, num = config.geometry, config.physics, config.numerics
        self.n_nodes = num.grid_resolution
        self.r_nodes = np.linspace(0.0, geo.anode_radius_m, self.n_nodes)
        self.h = float(self.r_nodes[1] - self.r_nodes[0])
        self.volumes = shell_volumes(self.n_nodes, self.h)

        for sc in config.run_control.stop_conditions:
            self._check_stop_metric(sc)

        # solve di prova: verifica subito che il catodo cada su un nodo interno
        probe = self.poisson.solve(geo, phys.cathode_voltage_v, self.n_nodes)
        self.r_cathode = probe.snapped_cathode_radius_m
        self.r_anode = geo.anode_radius_m

        # gas di fondo (bersaglio della fusione beam-target); per D-T si
        # assume miscela 50/50, solo la metà T è bersaglio del deutone
        self.n_background = phys.pressure_pa / (K_B * phys.gas_temperature_k)
        self.bg_target_fraction = 0.5 if phys.gas_species.value == "D-T" else 1.0

        # il peso macro lega il budget di macro-particelle alla sorgente fisica
        total_real_ions = phys.ion_source_rate_per_s * num.dt_s * config.run_control.max_steps
        self.macro_weight = total_real_ions / num.n_particles
        self.inject_per_step = num.n_particles / config.run_control.max_steps
        self._inject_acc = 0.0

        # stato particelle (SoA)
        self.r = np.empty(0)
        self.v = np.empty(0)  # velocità radiale
        self.ang_mom = np.empty(0)

        self.step_count = 0
        self.sim_time = 0.0
        self._t0 = time.perf_counter()
        self.field: RadialPotential = probe

        # contabilità cumulativa di onestà numerica
        self.cum_energy_drift_j = 0.0
        self.cum_field_work_j = 0.0
        self._reset_window()

    # ------------------------------------------------------------- loop

    def run(self) -> Iterator[SimState]:
        rc = self.config.run_control
        while self.step_count < rc.max_steps:
            self._step()
            if self.step_count % rc.snapshot_interval == 0 or self.step_count == rc.max_steps:
                diagnostics = self._diagnostics()
                done = self.step_count == rc.max_steps or self._stop_triggered(diagnostics)
                yield self._make_state(diagnostics, done)
                self._reset_window()
                if done:
                    return

    def _step(self) -> None:
        if self.step_count % self.field_update_every == 0:
            self.field = self._solve_field()
        self._push(self.field)
        self._inject()
        self.step_count += 1
        self.sim_time += self.config.numerics.dt_s

    def _solve_field(self) -> RadialPotential:
        rho = deposit_charge(self.r, self.macro_weight, self.h, self.volumes)
        return self.poisson.solve(
            self.config.geometry,
            self.config.physics.cathode_voltage_v,
            self.n_nodes,
            charge_density_c_per_m3=rho,
        )

    def _push(self, field: RadialPotential) -> None:
        if not self.r.size:
            return
        dt = self.config.numerics.dt_s
        w = self.macro_weight
        nodes, phi = self.r_nodes, field.phi_v

        r0, v0, ell = self.r, self.v, self.ang_mom
        ke0 = self._kinetic(r0, v0, ell)

        # kick (solo campo elettrico, mezzo passo)
        v_half = v0 + 0.5 * dt * (Q_E / M_D) * self._gather_e(r0, phi)

        # drift libero esatto: R(t) = R0 + V*t in 3D, proiettato su (r, v_r).
        # Gestisce pericentro e passaggio per il centro senza singolarità.
        v_t0 = ell / (M_D * np.maximum(r0, _R_TINY))
        v_sq = v_half**2 + v_t0**2
        r1 = np.sqrt(r0**2 + 2.0 * r0 * v_half * dt + v_sq * dt**2)
        v_r1 = (r0 * v_half + v_sq * dt) / np.maximum(r1, _R_TINY)

        hit_wall = r1 >= self.r_anode
        r1c = np.minimum(r1, self.r_anode)

        # kick (mezzo passo)
        v1 = v_r1 + 0.5 * dt * (Q_E / M_D) * self._gather_e(r1c, phi)
        ke1 = self._kinetic(r1c, v1, ell)

        # lavoro del campo (esatto per campo statico: q * caduta di potenziale)
        work = Q_E * (np.interp(r0, nodes, phi) - np.interp(r1c, nodes, phi))
        self.window_field_work_j += float(work.sum()) * w
        self.cum_field_work_j += float(np.abs(work).sum()) * w
        self.cum_energy_drift_j += float(np.abs((ke1 - ke0) - work).sum()) * w
        self.window_max_cfl = max(
            self.window_max_cfl, float(np.max(np.abs(v_half))) * dt / self.h
        )

        # griglia catodica: intercettazione probabilistica a ogni attraversamento
        crossed = ((r0 - self.r_cathode) * (r1c - self.r_cathode) < 0.0) & ~hit_wall
        unlucky = self.rng.random(r0.size) >= self.config.geometry.grid_transparency
        hit_grid = crossed & unlucky
        self.window_crossings += int(crossed.sum())
        self.window_crossings_survived += int((crossed & ~unlucky).sum())

        self.window_grid_energy_j += float(ke1[hit_grid].sum()) * w
        self.window_escape_energy_j += float(ke1[hit_wall].sum()) * w

        keep = ~(hit_wall | hit_grid)
        self.r, self.v, self.ang_mom = r1c[keep], v1[keep], ell[keep]

        # tasso di fusione istantaneo (beam-target su gas neutro)
        if self.r.size:
            ke = ke1[keep]
            speed = np.sqrt(2.0 * ke / M_D)
            sigma_tot, sigma_n = cross_sections_m2(
                self.config.physics.gas_species, ke / _KEV_J
            )
            n_t = self.n_background * self.bg_target_fraction
            self.window_fusion_rate_sum += float((n_t * sigma_tot * speed).sum()) * w
            self.window_neutron_rate_sum += float((n_t * sigma_n * speed).sum()) * w
        self.window_steps += 1

    def _inject(self) -> None:
        self._inject_acc += self.inject_per_step
        k = int(self._inject_acc)
        if k == 0:
            return
        self._inject_acc -= k
        r, v_r, ell = sample_injection(
            self.rng,
            k,
            self.r_cathode,
            self.r_anode,
            self.config.physics.gas_temperature_k,
        )
        self.r = np.concatenate([self.r, r])
        self.v = np.concatenate([self.v, v_r])
        self.ang_mom = np.concatenate([self.ang_mom, ell])

    # ------------------------------------------------------ diagnostica

    def _gather_e(self, r: np.ndarray, phi: np.ndarray) -> np.ndarray:
        """Campo elettrico staggered: E costante a tratti per cella, -dphi/h.

        Coerente ESATTAMENTE con l'interpolazione lineare del potenziale
        usata nella contabilità del lavoro: senza questa coerenza ogni
        attraversamento dello spigolo di potenziale al catodo accumula un
        errore energetico fisso, indipendente dal passo temporale.
        """
        i = np.clip((r / self.h).astype(int), 0, self.n_nodes - 2)
        return -(phi[i + 1] - phi[i]) / self.h

    def _kinetic(self, r: np.ndarray, v_r: np.ndarray, ell: np.ndarray) -> np.ndarray:
        v_t = ell / (M_D * np.maximum(r, _R_TINY))
        return 0.5 * M_D * (v_r**2 + v_t**2)

    def _diagnostics(self) -> Diagnostics:
        dt = self.config.numerics.dt_s
        steps = max(self.window_steps, 1)
        window_t = steps * dt

        fusion_rate = self.window_fusion_rate_sum / steps
        neutron_rate = self.window_neutron_rate_sum / steps
        grid_w = self.window_grid_energy_j / window_t
        escape_w = self.window_escape_energy_j / window_t

        ke = self._kinetic(self.r, self.v, self.ang_mom)
        spectrum, _ = np.histogram(
            ke / _EV_J,
            bins=_SPECTRUM_BINS,
            range=(0.0, 1.2 * abs(self.config.physics.cathode_voltage_v)),
            weights=np.full(ke.size, self.macro_weight),
        )
        recirc = (
            self.window_crossings_survived / self.window_crossings
            if self.window_crossings
            else 1.0
        )
        p_fus = fusion_rate * ENERGY_PER_FUSION_J[self.config.physics.gas_species]
        return Diagnostics(
            fusion_rate_per_s=fusion_rate,
            neutron_rate_per_s=neutron_rate,
            ion_energy_spectrum_ev=spectrum,
            grid_loss_w=grid_w,
            recirculation_efficiency=recirc,
            power_balance_w=p_fus - (grid_w + escape_w),
        )

    def _health(self) -> Health:
        err = self.cum_energy_drift_j / max(self.cum_field_work_j, 1e-300)
        warnings = []
        if self.window_max_cfl > 1.0:
            warnings.append(
                f"CFL particellare {self.window_max_cfl:.2g} > 1: "
                "spostamento per step oltre una cella"
            )
        return Health(
            energy_conservation_error=err,
            cfl_number=self.window_max_cfl,
            warnings=tuple(warnings),
        )

    def _lawson_triple(self) -> float:
        """n * T * tau_E in keV*s/m^3, stimato nel nucleo (r < raggio catodo)."""
        if not self.r.size:
            return 0.0
        ke = self._kinetic(self.r, self.v, self.ang_mom)
        core = self.r < self.r_cathode
        core_volume = (4.0 / 3.0) * np.pi * self.r_cathode**3
        n_core = (core.sum() * self.macro_weight) / core_volume
        ke_ref = ke[core] if np.any(core) else ke
        t_kev = (2.0 / 3.0) * float(ke_ref.mean()) / _KEV_J
        loss_power = (
            self.window_grid_energy_j + self.window_escape_energy_j
        ) / max(self.window_steps * self.config.numerics.dt_s, 1e-300)
        plasma_energy = float(ke.sum()) * self.macro_weight
        tau = plasma_energy / loss_power if loss_power > 0 else self.sim_time
        return n_core * t_kev * tau

    # ------------------------------------------------------- assemblaggio

    def _make_state(self, diagnostics: Diagnostics, done: bool) -> SimState:
        health = self._health()
        window_t = max(self.window_steps, 1) * self.config.numerics.dt_s
        verdict = build_verdict(
            gas_species=self.config.physics.gas_species,
            fusion_rate_per_s=diagnostics.fusion_rate_per_s,
            neutron_rate_per_s=diagnostics.neutron_rate_per_s,
            input_power_w=max(self.window_field_work_j / window_t, 0.0),
            grid_loss_w=diagnostics.grid_loss_w,
            escape_loss_w=self.window_escape_energy_j / window_t,
            lawson_triple_kev_s_m3=self._lawson_triple(),
            health=health,
        )

        alive = self.r.size
        k = min(alive, _VIZ_SAMPLE_MAX)
        idx = self.rng.choice(alive, size=k, replace=False) if alive else np.empty(0, int)
        ke = self._kinetic(self.r[idx], self.v[idx], self.ang_mom[idx])

        rho = deposit_charge(self.r, self.macro_weight, self.h, self.volumes)
        return SimState(
            kind="checkpoint" if done else "snapshot",
            meta=SimMeta(
                step=self.step_count,
                sim_time_s=self.sim_time,
                status=RunStatus.DONE if done else RunStatus.RUNNING,
                wall_clock_s=time.perf_counter() - self._t0,
            ),
            fields=FieldSnapshot(
                potential_v=self.field.phi_v,
                e_field_v_per_m=self.field.e_r_v_per_m,
                charge_density_c_per_m3=rho,
            ),
            particles=ParticleSample(
                positions_m=self.r[idx],
                velocities_m_per_s=self.v[idx],
                energies_ev=ke / _EV_J,
                sample_fraction=k / alive if alive else 1.0,
            ),
            diagnostics=diagnostics,
            health=health,
            physics_verdict=verdict,
        )

    # ---------------------------------------------------------- supporto

    def _reset_window(self) -> None:
        self.window_steps = 0
        self.window_fusion_rate_sum = 0.0
        self.window_neutron_rate_sum = 0.0
        self.window_grid_energy_j = 0.0
        self.window_escape_energy_j = 0.0
        self.window_field_work_j = 0.0
        self.window_crossings = 0
        self.window_crossings_survived = 0
        self.window_max_cfl = 0.0

    def _check_stop_metric(self, sc: StopCondition) -> None:
        valid = [
            name
            for name, f in Diagnostics.model_fields.items()
            if name != "ion_energy_spectrum_ev"
        ]
        if sc.metric not in valid:
            raise ValueError(
                f"Metrica di stop sconosciuta '{sc.metric}' (valide: {valid})"
            )

    def _stop_triggered(self, diagnostics: Diagnostics) -> bool:
        return any(
            _OPS[sc.op](getattr(diagnostics, sc.metric), sc.threshold)
            for sc in self.config.run_control.stop_conditions
        )
