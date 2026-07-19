"""Motore tokamak: equilibrio 2D statico + bilancio di potenza 0D dinamico.

Modello dichiarato (0D, "systems code" didattico):
    dW/dt = P_aux + P_alfa - P_brems - W / tau_E
con
- W = 3 n T V (elettroni + ioni alla stessa temperatura),
- P_fusione da reattività termica D-T di Bosch-Hale; le alfa (3.52 dei
  17.59 MeV) restano nel plasma, i neutroni escono,
- P_brems = 5.35e-37 * n^2 * sqrt(T_keV) * V (Z_eff = 1),
- tau_E dallo scaling empirico H-mode IPB98(y,2), moltiplicato per H.

È il modello con cui si fanno gli studi di sistema dei reattori veri:
niente turbolenza né profili, ma la fisica del pareggio c'è tutta —
incluso l'innesco (le alfa che riscaldano il plasma da sole).
Integrazione RK4 con stima d'errore per passo doppio/mezzo: l'errore
misurato alimenta l'affidabilità del referto, come nel fusore.

Cosa NON è modellato (dichiarato): profili radiali, impurità e Z_eff,
limiti operativi (densità di Greenwald, beta), disruzioni, ELM.
"""

import time
from collections.abc import Iterator

import numpy as np

from fusor_sim.catalog import get_equilibrium_solver
from fusor_sim.contracts.physics_verdict import (
    LossBreakdown,
    NumericalReliability,
    PhysicsVerdict,
)
from fusor_sim.contracts.sim_state import Health, RunStatus, SimMeta
from fusor_sim.contracts.tokamak import (
    TokamakDiagnostics,
    TokamakFluxMap,
    TokamakRunConfig,
    TokamakState,
)
from fusor_sim.engine.fusion import (
    E_DT_ALPHA_J,
    E_DT_TOTAL_J,
    SIGMAV_DT_VALID_KEV,
    sigmav_dt_m3_s,
)
from fusor_sim.engine.simulation import _OPS

_KEV_J = 1.602176634e-16
_BREMS_COEF = 5.35e-37  # W m^3 keV^-1/2, Z_eff = 1
_LAWSON_DT_KEV_S_M3 = 3e21
_T_START_KEV = 0.5
_FUEL_MASS_AMU = 2.5  # miscela D-T 50/50


class Tokamak0DEngine:
    """Motore del catalogo: id tokamak_0d_v1."""

    engine_id = "tokamak_0d_v1"
    pusher_id = engine_id  # alias per il registro comune dei motori

    def __init__(self, config: TokamakRunConfig, seed: int = 0):
        if config.solver_selection.engine_id != self.engine_id:
            raise ValueError(
                f"Questo motore è '{self.engine_id}', la config chiede "
                f"'{config.solver_selection.engine_id}'"
            )
        self.config = config
        geo = config.geometry
        self.volume = geo.plasma_volume_m3
        self.n = config.physics.density_1e19_m3 * 1e19

        solver = get_equilibrium_solver(config.solver_selection.equilibrium_solver_id)
        self.flux = solver.solve(geo, n_nodes=config.numerics.grid_resolution)

        self.w_j = 3.0 * self.n * _T_START_KEV * _KEV_J * self.volume
        self.step_count = 0
        self.sim_time = 0.0
        self._t0 = time.perf_counter()
        self.max_local_error = 0.0
        self.t_out_of_range = False

        for sc in config.run_control.stop_conditions:
            if sc.metric not in TokamakDiagnostics.model_fields:
                raise ValueError(
                    f"Metrica di stop sconosciuta '{sc.metric}' "
                    f"(valide: {sorted(TokamakDiagnostics.model_fields)})"
                )

    # ------------------------------------------------------------ fisica

    def _t_kev(self, w_j: float) -> float:
        return w_j / (3.0 * self.n * self.volume) / _KEV_J

    def _powers(self, w_j: float) -> dict:
        t_kev = self._t_kev(w_j)
        sv = sigmav_dt_m3_s(t_kev)
        p_fus = (self.n / 2.0) ** 2 * sv * E_DT_TOTAL_J * self.volume
        p_alpha = p_fus * (E_DT_ALPHA_J / E_DT_TOTAL_J)
        p_aux = self.config.physics.aux_heating_mw * 1e6
        p_brems = _BREMS_COEF * self.n**2 * np.sqrt(max(t_kev, 1e-6)) * self.volume
        tau = self._tau_e(p_aux + p_alpha)
        return dict(
            t_kev=t_kev, p_fus=p_fus, p_alpha=p_alpha, p_aux=p_aux,
            p_brems=p_brems, tau=tau, p_transport=w_j / tau,
        )

    def _tau_e(self, heating_w: float) -> float:
        """Scaling IPB98(y,2), moltiplicato per il fattore H."""
        geo = self.config.geometry
        p_mw = max(heating_w / 1e6, 0.1)
        n19 = self.config.physics.density_1e19_m3
        eps = geo.minor_radius_m / geo.major_radius_m
        tau = (
            0.0562
            * geo.plasma_current_ma**0.93
            * geo.toroidal_field_t**0.15
            * p_mw**-0.69
            * n19**0.41
            * _FUEL_MASS_AMU**0.19
            * geo.major_radius_m**1.97
            * eps**0.58
            * geo.elongation**0.78
        )
        return self.config.physics.h_factor * tau

    def _dwdt(self, w_j: float) -> float:
        p = self._powers(max(w_j, 0.0))
        return p["p_aux"] + p["p_alpha"] - p["p_brems"] - p["p_transport"]

    def _rk4(self, w: float, dt: float) -> float:
        k1 = self._dwdt(w)
        k2 = self._dwdt(w + 0.5 * dt * k1)
        k3 = self._dwdt(w + 0.5 * dt * k2)
        k4 = self._dwdt(w + dt * k3)
        return max(w + dt / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4), 0.0)

    # -------------------------------------------------------------- loop

    def run(self) -> Iterator[TokamakState]:
        rc = self.config.run_control
        dt = self.config.numerics.dt_s
        while self.step_count < rc.max_steps:
            # passo intero vs due mezzi: stima onesta dell'errore locale
            w_full = self._rk4(self.w_j, dt)
            w_half = self._rk4(self._rk4(self.w_j, dt / 2.0), dt / 2.0)
            if w_half > 0:
                self.max_local_error = max(
                    self.max_local_error, abs(w_full - w_half) / w_half
                )
            self.w_j = w_half
            t_now = self._t_kev(self.w_j)
            if not SIGMAV_DT_VALID_KEV[0] <= t_now <= SIGMAV_DT_VALID_KEV[1]:
                self.t_out_of_range = True
            self.step_count += 1
            self.sim_time += dt

            if self.step_count % rc.snapshot_interval == 0 or self.step_count == rc.max_steps:
                diagnostics = self._diagnostics()
                done = self.step_count == rc.max_steps or self._stop(diagnostics)
                yield self._make_state(diagnostics, done)
                if done:
                    return

    def _stop(self, diagnostics: TokamakDiagnostics) -> bool:
        return any(
            _OPS[sc.op](getattr(diagnostics, sc.metric), sc.threshold)
            for sc in self.config.run_control.stop_conditions
        )

    # ------------------------------------------------------- diagnostica

    def _diagnostics(self) -> TokamakDiagnostics:
        p = self._powers(self.w_j)
        q = p["p_fus"] / p["p_aux"] if p["p_aux"] > 0 else 0.0
        return TokamakDiagnostics(
            t_kev=p["t_kev"],
            plasma_energy_j=self.w_j,
            fusion_power_w=p["p_fus"],
            alpha_power_w=p["p_alpha"],
            aux_power_w=p["p_aux"],
            brems_power_w=p["p_brems"],
            transport_power_w=p["p_transport"],
            tau_e_s=p["tau"],
            q_factor=q,
            triple_product_kev_s_m3=self.n * p["t_kev"] * p["tau"],
            neutron_rate_per_s=p["p_fus"] / E_DT_TOTAL_J,
        )

    def _health(self) -> Health:
        dt_ratio = self.config.numerics.dt_s / max(self._powers(self.w_j)["tau"], 1e-9)
        warnings = []
        if self.t_out_of_range:
            warnings.append(
                "temperatura fuori dal range di validità di Bosch-Hale (0.2-100 keV)"
            )
        if dt_ratio > 0.5:
            warnings.append(f"passo temporale {dt_ratio:.2g}*tau_E: dinamica sottorisolta")
        err = self.max_local_error if not self.t_out_of_range else max(
            self.max_local_error, 1.0
        )
        return Health(
            energy_conservation_error=err,
            cfl_number=dt_ratio,
            warnings=tuple(warnings),
        )

    def _make_state(self, diagnostics: TokamakDiagnostics, done: bool) -> TokamakState:
        health = self._health()
        return TokamakState(
            kind="checkpoint" if done else "snapshot",
            meta=SimMeta(
                step=self.step_count,
                sim_time_s=self.sim_time,
                status=RunStatus.DONE if done else RunStatus.RUNNING,
                wall_clock_s=time.perf_counter() - self._t0,
            ),
            flux=TokamakFluxMap(
                r_axis_m=self.flux.r_axis_m,
                z_axis_m=self.flux.z_axis_m,
                psi=self.flux.psi,
                psi_boundary=self.flux.psi_boundary,
                magnetic_axis_r_m=self.flux.magnetic_axis_r_m,
            ),
            diagnostics=diagnostics,
            health=health,
            physics_verdict=self._verdict(diagnostics, health),
        )

    def _verdict(
        self, d: TokamakDiagnostics, health: Health
    ) -> PhysicsVerdict:
        if health.energy_conservation_error < 0.02 and health.cfl_number <= 0.5:
            reliability = NumericalReliability.RELIABLE
        elif health.energy_conservation_error < 0.10 and health.cfl_number <= 1.0:
            reliability = NumericalReliability.MARGINAL
        else:
            reliability = NumericalReliability.UNRELIABLE

        losses = LossBreakdown(
            grid_w=0.0,  # nessuna griglia nel plasma: il vantaggio strutturale
            radiation_w=d.brems_power_w,
            conduction_w=d.transport_power_w,
            escape_w=0.0,
        )
        if reliability is NumericalReliability.UNRELIABLE:
            return PhysicsVerdict(
                numerical_reliability=reliability,
                produces_fusion=None,
                fusion_rate_per_s=None,
                fusion_power_w=None,
                input_power_w=d.aux_power_w,
                net_energy_balance_w=None,
                loss_breakdown=losses,
                lawson_distance_orders=None,
                honest_summary=(
                    "RISULTATO NON AFFIDABILE: "
                    + ("; ".join(health.warnings) or "integrazione fuori tolleranza")
                    + ". Nessun numero di fusione viene riportato."
                ),
            )

        orders = float(
            np.log10(_LAWSON_DT_KEV_S_M3 / max(d.triple_product_kev_s_m3, 1e-30))
        )
        lawson_txt = (
            f"OLTRE la soglia di Lawson di {-orders:.1f} ordini di grandezza"
            if orders < 0
            else f"a {orders:.1f} ordini di grandezza dalla soglia di Lawson"
        )
        summary = (
            f"Tokamak (modello 0D, scaling IPB98(y,2), equilibrio Solov'ev): "
            f"T = {d.t_kev:.1f} keV, tau_E = {d.tau_e_s:.2f} s. "
            f"Fusione: {'sì' if d.fusion_power_w > 0 else 'no'} "
            f"({d.fusion_power_w/1e6:.3g} MW, {d.neutron_rate_per_s:.3g} neutroni/s), "
            f"Q = {d.q_factor:.2f} con {d.aux_power_w/1e6:.3g} MW ausiliari. "
            f"Il plasma è {lawson_txt}. Perdite: trasporto "
            f"{d.transport_power_w/1e6:.3g} MW, radiazione {d.brems_power_w/1e6:.3g} MW — "
            "e zero perdite su griglia: non c'è nessun oggetto materiale nel plasma. "
            "Non modellati: profili radiali, impurità, limiti operativi "
            "(Greenwald, beta), disruzioni."
        )
        if reliability is NumericalReliability.MARGINAL:
            summary += " AVVERTENZA: risoluzione temporale al limite."
        return PhysicsVerdict(
            numerical_reliability=reliability,
            produces_fusion=d.fusion_power_w > 0,
            fusion_rate_per_s=d.neutron_rate_per_s,
            fusion_power_w=d.fusion_power_w,
            input_power_w=d.aux_power_w,
            net_energy_balance_w=d.fusion_power_w - d.aux_power_w,
            loss_breakdown=losses,
            lawson_distance_orders=orders,
            honest_summary=summary,
        )
