"""RunConfig: input al motore di simulazione, immutabile durante un run.

Cinque gruppi, ognuno con un proprietario diverso (vedi ownership.py):
geometry e physics dall'utente, numerics dall'auto-tuner, solver_selection
dal router, run_control dall'orchestratore. Tutti i modelli sono frozen:
una RunConfig emessa non si modifica, se ne emette una nuova.

Unità SI esplicite nei nomi dei campi (_m, _v, _pa, _k, _s).
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class GasSpecies(str, Enum):
    """Specie di combustibile: deuterio-deuterio o deuterio-trizio."""

    DD = "D-D"
    DT = "D-T"


class GeometryConfig(BaseModel):
    """Geometria sferica del fusore. Proprietario: utente."""

    model_config = _FROZEN

    geometry_type: Literal["spherical"] = "spherical"
    chamber_radius_m: float = Field(gt=0, le=2.0, description="Raggio della camera a vuoto")
    anode_radius_m: float = Field(gt=0, description="Raggio della griglia esterna (anodo)")
    cathode_radius_m: float = Field(gt=0, description="Raggio della griglia interna (catodo)")
    grid_transparency: float = Field(
        gt=0.0, lt=1.0, description="Frazione geometrica aperta della griglia catodica"
    )
    # spostamento del catodo dal centro. Con offset != 0 la configurazione
    # è realizzabile ma NON giudicabile dai solver attuali (solo anteprima campo)
    cathode_offset_x_m: float = Field(default=0.0, ge=-1.0, le=1.0)
    cathode_offset_y_m: float = Field(default=0.0, ge=-1.0, le=1.0)
    cathode_offset_z_m: float = Field(default=0.0, ge=-1.0, le=1.0)

    @property
    def cathode_offset_magnitude_m(self) -> float:
        return (
            self.cathode_offset_x_m**2
            + self.cathode_offset_y_m**2
            + self.cathode_offset_z_m**2
        ) ** 0.5

    @property
    def is_concentric(self) -> bool:
        return self.cathode_offset_magnitude_m < 1e-12

    @model_validator(mode="after")
    def _radii_ordered(self) -> "GeometryConfig":
        if not (self.cathode_radius_m < self.anode_radius_m <= self.chamber_radius_m):
            raise ValueError(
                "Geometria non realizzabile: serve "
                "raggio catodo < raggio anodo <= raggio camera "
                f"(catodo={self.cathode_radius_m} m, anodo={self.anode_radius_m} m, "
                f"camera={self.chamber_radius_m} m)"
            )
        if self.cathode_offset_magnitude_m + self.cathode_radius_m >= self.anode_radius_m:
            raise ValueError(
                "Geometria non realizzabile: il catodo spostato di "
                f"{self.cathode_offset_magnitude_m:.4g} m uscirebbe dall'anodo "
                f"(raggio catodo {self.cathode_radius_m} m, anodo {self.anode_radius_m} m)"
            )
        return self


class PhysicsConfig(BaseModel):
    """Condizioni fisiche operative. Proprietario: utente."""

    model_config = _FROZEN

    cathode_voltage_v: float = Field(
        lt=0,
        ge=-500_000,
        description="Tensione del catodo rispetto alla camera (negativa: accelera gli ioni verso il centro)",
    )
    gas_species: GasSpecies
    pressure_pa: float = Field(
        ge=1e-4, le=100.0, description="Pressione del gas nella camera"
    )
    ion_source_rate_per_s: float = Field(
        gt=0, le=1e22, description="Tasso di produzione ioni della sorgente"
    )
    gas_temperature_k: float = Field(gt=0, le=2000.0, description="Temperatura del gas neutro")


class NumericsConfig(BaseModel):
    """Parametri numerici. Proprietario: auto-tuner (mai l'utente, mai la chat)."""

    model_config = _FROZEN

    grid_resolution: int = Field(ge=16, le=1024, description="Punti griglia per dimensione")
    n_particles: int = Field(ge=1_000, le=200_000_000, description="Macro-particelle PIC")
    dt_s: float = Field(gt=0, le=1e-6, description="Passo temporale")
    precision: Literal["float32", "float64"] = "float64"
    cuda_block_size: int = Field(default=256, ge=32, le=1024)

    @field_validator("cuda_block_size")
    @classmethod
    def _block_multiple_of_warp(cls, v: int) -> int:
        if v % 32 != 0:
            raise ValueError("cuda_block_size deve essere multiplo di 32 (dimensione warp)")
        return v


class SolverSelection(BaseModel):
    """Solver scelti dal catalogo di implementazioni validate. Proprietario: router."""

    model_config = _FROZEN

    poisson_solver_id: str = Field(min_length=1)
    pusher_id: str = Field(min_length=1)


class StopCondition(BaseModel):
    """Condizione di arresto su una metrica diagnostica, es. ('grid_loss_w', '>', 1e4)."""

    model_config = _FROZEN

    metric: str = Field(min_length=1)
    op: Literal["<", "<=", ">", ">="]
    threshold: float


class RunControl(BaseModel):
    """Controllo del run. Proprietario: orchestratore."""

    model_config = _FROZEN

    max_steps: int = Field(ge=1, le=10_000_000)
    snapshot_interval: int = Field(ge=1, description="Ogni quanti step un snapshot leggero per il viz")
    checkpoint_interval: int = Field(ge=1, description="Ogni quanti step un checkpoint completo su disco")
    stop_conditions: tuple[StopCondition, ...] = ()

    @model_validator(mode="after")
    def _checkpoint_not_denser_than_snapshot(self) -> "RunControl":
        if self.checkpoint_interval < self.snapshot_interval:
            raise ValueError(
                "checkpoint_interval < snapshot_interval: i checkpoint completi "
                "sono rari, gli snapshot leggeri frequenti"
            )
        return self


class RunConfig(BaseModel):
    """Configurazione completa di un run. Immutabile: si sostituisce, non si modifica."""

    model_config = _FROZEN

    geometry: GeometryConfig
    physics: PhysicsConfig
    numerics: NumericsConfig
    solver_selection: SolverSelection
    run_control: RunControl


def example_run_config() -> RunConfig:
    """RunConfig di riferimento: un fusore amatoriale tipico (per test e sviluppo)."""
    return RunConfig(
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
        numerics=NumericsConfig(
            grid_resolution=128,
            n_particles=500_000,
            dt_s=1e-9,
            precision="float64",
        ),
        solver_selection=SolverSelection(
            poisson_solver_id="poisson_spherical_fd_v1",
            pusher_id="leapfrog_radial_v1",
        ),
        run_control=RunControl(
            max_steps=100_000,
            snapshot_interval=100,
            checkpoint_interval=10_000,
        ),
    )
