"""PhysicsVerdict: il referto di onestà fisica.

Il motore non restituisce mai un risultato senza questo referto (SimState
lo richiede come campo obbligatorio). Due regole di onestà sono codificate
strutturalmente nei validatori:

1. produces_fusion non è un'opinione: deve coincidere con fusion_rate_per_s > 0.
2. Se il risultato è numericamente inaffidabile (conservazione dell'energia
   violata oltre soglia), i numeri di fusione DEVONO essere None: un numero
   inaffidabile non si riporta, punto.
3. Un referto con scope "field_only" (anteprima del solo campo elettrostatico,
   nessuna dinamica particellare) non può riportare NESSUN numero di fusione:
   mostrare la fisica che c'è, non inventare quella che non è stata calcolata.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class NumericalReliability(str, Enum):
    RELIABLE = "reliable"
    MARGINAL = "marginal"  # al limite: riportare i numeri con avvertenza
    UNRELIABLE = "unreliable"  # non riportare i numeri


class LossBreakdown(BaseModel):
    """Dove va l'energia. Nel fusore la griglia è quasi sempre la perdita dominante."""

    model_config = _FROZEN

    grid_w: float = Field(ge=0, description="Ioni intercettati dalla griglia catodica")
    radiation_w: float = Field(ge=0, description="Bremsstrahlung e altre radiazioni")
    conduction_w: float = Field(ge=0, description="Conduzione/convezione verso le pareti")
    escape_w: float = Field(ge=0, description="Particelle veloci che sfuggono al confinamento")

    @property
    def total_w(self) -> float:
        return self.grid_w + self.radiation_w + self.conduction_w + self.escape_w


class PhysicsVerdict(BaseModel):
    """Referto fisico obbligatorio: accompagna ogni SimState, mai omesso."""

    model_config = _FROZEN

    scope: Literal["full", "field_only"] = Field(
        default="full",
        description="full = run completo; field_only = anteprima del solo campo",
    )
    numerical_reliability: NumericalReliability
    produces_fusion: bool | None = Field(
        description="None solo se il risultato è numericamente inaffidabile"
    )
    fusion_rate_per_s: float | None = Field(ge=0, description="Reazioni di fusione al secondo")
    fusion_power_w: float | None = Field(ge=0)
    input_power_w: float = Field(ge=0, description="Potenza elettrica immessa")
    net_energy_balance_w: float | None = Field(
        description="P_fusione - P_perdite (quasi sempre profondamente negativo)"
    )
    loss_breakdown: LossBreakdown
    lawson_distance_orders: float | None = Field(
        description="Ordini di grandezza sotto la soglia di Lawson (positivo = sotto soglia)"
    )
    honest_summary: str = Field(
        min_length=1, description="Verdetto in linguaggio comprensibile a chiunque"
    )

    @model_validator(mode="after")
    def _honesty_rules(self) -> "PhysicsVerdict":
        numeric_fields = {
            "produces_fusion": self.produces_fusion,
            "fusion_rate_per_s": self.fusion_rate_per_s,
            "fusion_power_w": self.fusion_power_w,
            "net_energy_balance_w": self.net_energy_balance_w,
            "lawson_distance_orders": self.lawson_distance_orders,
        }
        if self.scope == "field_only":
            reported = [k for k, v in numeric_fields.items() if v is not None]
            if reported:
                raise ValueError(
                    "Anteprima del solo campo: nessuna dinamica particellare è stata "
                    f"calcolata, i campi di fusione devono essere None ({', '.join(reported)})"
                )
        elif self.numerical_reliability is NumericalReliability.UNRELIABLE:
            reported = [k for k, v in numeric_fields.items() if v is not None]
            if reported:
                raise ValueError(
                    "Risultato numericamente inaffidabile: i campi di fusione devono "
                    f"essere None, non riportati ({', '.join(reported)}). "
                    "Un numero inaffidabile non si comunica."
                )
        else:
            missing = [k for k, v in numeric_fields.items() if v is None]
            if missing:
                raise ValueError(
                    "Risultato affidabile ma referto incompleto: mancano "
                    f"{', '.join(missing)}. Il referto è obbligatorio in ogni sua parte."
                )
            if self.produces_fusion != (self.fusion_rate_per_s > 0):
                raise ValueError(
                    "Incoerenza nel referto: produces_fusion deve coincidere con "
                    f"fusion_rate_per_s > 0 (dichiarato {self.produces_fusion}, "
                    f"tasso {self.fusion_rate_per_s}/s)"
                )
        return self
