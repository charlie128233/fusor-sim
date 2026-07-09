"""FieldPreview: anteprima del solo campo elettrostatico in 3D.

Non è un run: nessuna particella, nessuna fusione. Serve per geometrie
che il catalogo non sa ancora giudicare (es. catodo fuori centro) o come
verifica visiva prima di un run. Come ogni risultato del simulatore,
porta OBBLIGATORIAMENTE il suo referto — con scope "field_only", quindi
strutturalmente privo di numeri di fusione.
"""

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fusor_sim.contracts.physics_verdict import PhysicsVerdict


class FieldPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    grid_extent_m: float = Field(gt=0, description="Semilato del cubo di calcolo")
    n_nodes: int = Field(ge=16, description="Nodi per dimensione")
    slice_z0_v: np.ndarray  # potenziale sul piano z=0 (n x n)
    slice_y0_v: np.ndarray  # potenziale sul piano y=0 (n x n)
    cathode_offset_m: tuple[float, float, float]
    converged: bool
    residual_rel: float = Field(ge=0)
    physics_verdict: PhysicsVerdict  # obbligatorio, scope field_only

    @model_validator(mode="after")
    def _honest_preview(self) -> "FieldPreview":
        if self.physics_verdict.scope != "field_only":
            raise ValueError(
                "Il referto di una FieldPreview deve avere scope 'field_only': "
                "un'anteprima di campo non giudica la fusione"
            )
        n = self.n_nodes
        for name, s in (("slice_z0_v", self.slice_z0_v), ("slice_y0_v", self.slice_y0_v)):
            if s.shape != (n, n):
                raise ValueError(f"{name} ha shape {s.shape}, attesa ({n}, {n})")
        return self
