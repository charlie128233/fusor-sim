"""Contratti del dominio tokamak.

Stessa disciplina del fusore: gruppi con proprietari distinti, modelli
frozen, verdetto obbligatorio. Il modello fisico è dichiarato nel motore:
equilibrio 2D di Grad-Shafranov (forma delle superfici di flusso) +
bilancio di potenza 0D con confinamento da scaling empirico IPB98(y,2).
"""

from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fusor_sim.contracts.physics_verdict import PhysicsVerdict
from fusor_sim.contracts.run_config import RunControl
from fusor_sim.contracts.sim_state import Health, SimMeta

_FROZEN = ConfigDict(frozen=True, extra="forbid")
_FROZEN_NP = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)


class TokamakGeometryConfig(BaseModel):
    """Geometria del toro e campo. Proprietario: utente."""

    model_config = _FROZEN

    geometry_type: Literal["tokamak"] = "tokamak"
    major_radius_m: float = Field(gt=0.3, le=12.0, description="Raggio maggiore R0")
    minor_radius_m: float = Field(gt=0.05, le=4.0, description="Raggio minore a")
    elongation: float = Field(ge=1.0, le=2.5, description="Elongazione kappa")
    toroidal_field_t: float = Field(gt=0.5, le=14.0, description="Campo toroidale B0")
    plasma_current_ma: float = Field(gt=0.1, le=20.0, description="Corrente di plasma")

    @model_validator(mode="after")
    def _aspect_ratio(self) -> "TokamakGeometryConfig":
        if self.minor_radius_m >= self.major_radius_m * 0.65:
            raise ValueError(
                "Geometria non realizzabile: raggio minore troppo grande "
                f"(a={self.minor_radius_m} m vs R0={self.major_radius_m} m: "
                "serve un rapporto d'aspetto R0/a > ~1.5)"
            )
        return self

    @property
    def plasma_volume_m3(self) -> float:
        return float(
            2.0 * np.pi**2 * self.major_radius_m * self.minor_radius_m**2 * self.elongation
        )


class TokamakPhysicsConfig(BaseModel):
    """Condizioni del plasma. Proprietario: utente. Combustibile: D-T
    (l'unico per cui un tokamak ha senso; vedi guida, lezione 5)."""

    model_config = _FROZEN

    fuel: Literal["D-T"] = "D-T"
    density_1e19_m3: float = Field(
        ge=0.1, le=50.0, description="Densità elettronica in unità di 1e19 m^-3"
    )
    aux_heating_mw: float = Field(
        ge=0.0, le=200.0, description="Potenza di riscaldamento ausiliario"
    )
    h_factor: float = Field(
        default=1.0, ge=0.5, le=1.5,
        description="Fattore H rispetto allo scaling IPB98(y,2)",
    )


class TokamakNumericsConfig(BaseModel):
    """Parametri numerici. Proprietario: auto-tuner."""

    model_config = _FROZEN

    grid_resolution: int = Field(ge=33, le=257, description="Nodi per lato (equilibrio)")
    dt_s: float = Field(gt=0, le=1.0, description="Passo del bilancio 0D")


class TokamakSolverSelection(BaseModel):
    """Solver dal catalogo. Proprietario: router."""

    model_config = _FROZEN

    equilibrium_solver_id: str = Field(min_length=1)
    engine_id: str = Field(min_length=1)


class TokamakRunConfig(BaseModel):
    model_config = _FROZEN

    geometry: TokamakGeometryConfig
    physics: TokamakPhysicsConfig
    numerics: TokamakNumericsConfig
    solver_selection: TokamakSolverSelection
    run_control: RunControl


class TokamakDiagnostics(BaseModel):
    model_config = _FROZEN

    t_kev: float = Field(ge=0, description="Temperatura del plasma")
    plasma_energy_j: float = Field(ge=0)
    fusion_power_w: float = Field(ge=0)
    alpha_power_w: float = Field(ge=0, description="Potenza delle alfa (resta nel plasma)")
    aux_power_w: float = Field(ge=0)
    brems_power_w: float = Field(ge=0)
    transport_power_w: float = Field(ge=0, description="Perdita di trasporto W/tau_E")
    tau_e_s: float = Field(ge=0, description="Tempo di confinamento (scaling)")
    q_factor: float = Field(ge=0, description="Q = P_fusione / P_ausiliaria")
    triple_product_kev_s_m3: float = Field(ge=0)
    neutron_rate_per_s: float = Field(ge=0)


class TokamakFluxMap(BaseModel):
    """Mappa di flusso dell'equilibrio (unità normalizzate, statica)."""

    model_config = _FROZEN_NP

    r_axis_m: np.ndarray
    z_axis_m: np.ndarray
    psi: np.ndarray
    psi_boundary: float
    magnetic_axis_r_m: float

    @model_validator(mode="after")
    def _shapes(self) -> "TokamakFluxMap":
        expected = (len(self.r_axis_m), len(self.z_axis_m))
        if self.psi.shape != expected:
            raise ValueError(f"psi ha shape {self.psi.shape}, attesa {expected}")
        return self


class TokamakState(BaseModel):
    """Stato emesso dal motore tokamak. Referto non omissibile."""

    model_config = _FROZEN_NP

    domain: Literal["tokamak"] = "tokamak"
    kind: Literal["snapshot", "checkpoint"]
    meta: SimMeta
    flux: TokamakFluxMap
    diagnostics: TokamakDiagnostics
    health: Health
    physics_verdict: PhysicsVerdict
