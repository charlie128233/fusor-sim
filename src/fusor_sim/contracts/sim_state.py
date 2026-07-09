"""SimState: output del motore di simulazione.

Due varianti dello stesso contratto:
- snapshot ("leggero", frequente): per il visualizzatore, particelle
  sottocampionate;
- checkpoint ("completo", raro): per pausa/ripresa su disco (HDF5).

Il physics_verdict è un campo obbligatorio senza default: è strutturalmente
impossibile costruire un SimState senza referto.
"""

from enum import Enum
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fusor_sim.contracts.physics_verdict import PhysicsVerdict

_FROZEN_NP = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)


class RunStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"


class SimMeta(BaseModel):
    model_config = _FROZEN_NP

    step: int = Field(ge=0)
    sim_time_s: float = Field(ge=0)
    status: RunStatus
    wall_clock_s: float = Field(ge=0)


class FieldSnapshot(BaseModel):
    """Campi su griglia: potenziale, campo elettrico, densità di carica."""

    model_config = _FROZEN_NP

    potential_v: np.ndarray
    e_field_v_per_m: np.ndarray
    charge_density_c_per_m3: np.ndarray

    @model_validator(mode="after")
    def _shapes_consistent(self) -> "FieldSnapshot":
        if self.potential_v.shape != self.charge_density_c_per_m3.shape:
            raise ValueError(
                "Shape incoerenti: potenziale "
                f"{self.potential_v.shape} vs densità di carica "
                f"{self.charge_density_c_per_m3.shape}"
            )
        return self


class ParticleSample(BaseModel):
    """Campione di particelle per il visualizzatore (mai l'intera popolazione)."""

    model_config = _FROZEN_NP

    positions_m: np.ndarray
    velocities_m_per_s: np.ndarray
    energies_ev: np.ndarray
    sample_fraction: float = Field(gt=0, le=1.0, description="Frazione della popolazione totale")

    @model_validator(mode="after")
    def _lengths_match(self) -> "ParticleSample":
        n = len(self.positions_m)
        if len(self.velocities_m_per_s) != n or len(self.energies_ev) != n:
            raise ValueError(
                f"Numero particelle incoerente: {n} posizioni, "
                f"{len(self.velocities_m_per_s)} velocità, {len(self.energies_ev)} energie"
            )
        return self


class Diagnostics(BaseModel):
    model_config = _FROZEN_NP

    fusion_rate_per_s: float = Field(ge=0)
    neutron_rate_per_s: float = Field(ge=0)
    ion_energy_spectrum_ev: np.ndarray = Field(description="Istogramma energie ioni")
    grid_loss_w: float = Field(ge=0)
    recirculation_efficiency: float = Field(ge=0, le=1.0)
    power_balance_w: float


class Health(BaseModel):
    """Salute numerica del run: alimenta numerical_reliability nel referto."""

    model_config = _FROZEN_NP

    energy_conservation_error: float = Field(
        ge=0, description="Errore relativo di conservazione dell'energia"
    )
    cfl_number: float = Field(ge=0)
    warnings: tuple[str, ...] = ()


class SimState(BaseModel):
    """Stato emesso dal motore. Il referto fisico non è omissibile."""

    model_config = _FROZEN_NP

    kind: Literal["snapshot", "checkpoint"]
    meta: SimMeta
    fields: FieldSnapshot
    particles: ParticleSample
    diagnostics: Diagnostics
    health: Health
    physics_verdict: PhysicsVerdict  # obbligatorio, nessun default
