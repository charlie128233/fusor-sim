"""Ownership dei gruppi della RunConfig.

Regola del documento di visione: tre gruppi, tre proprietari diversi.
Nessun attore tocca il campo di un altro. Questa mappa è l'unica fonte
di verità; l'orchestratore e ChatIntent la consultano per rifiutare
modifiche fuori competenza.
"""

from enum import Enum

from fusor_sim.contracts import run_config as _rc
from fusor_sim.contracts import tokamak as _tk


class Owner(str, Enum):
    USER = "user"
    ROUTER = "router"
    AUTO_TUNER = "auto_tuner"
    ORCHESTRATOR = "orchestrator"


GROUP_OWNERS: dict[str, Owner] = {
    "geometry": Owner.USER,
    "physics": Owner.USER,
    "numerics": Owner.AUTO_TUNER,
    "solver_selection": Owner.ROUTER,
    "run_control": Owner.ORCHESTRATOR,
    # dominio tokamak: stessi ruoli, gruppi con prefisso
    "tokamak_geometry": Owner.USER,
    "tokamak_physics": Owner.USER,
    "tokamak_numerics": Owner.AUTO_TUNER,
}

_GROUP_MODELS = {
    "geometry": _rc.GeometryConfig,
    "physics": _rc.PhysicsConfig,
    "numerics": _rc.NumericsConfig,
    "solver_selection": _rc.SolverSelection,
    "run_control": _rc.RunControl,
    "tokamak_geometry": _tk.TokamakGeometryConfig,
    "tokamak_physics": _tk.TokamakPhysicsConfig,
    "tokamak_numerics": _tk.TokamakNumericsConfig,
}


def owner_of(path: str) -> Owner:
    """Proprietario di un path nella RunConfig, es. 'physics.pressure_pa'.

    Solleva ValueError se il gruppo o il campo non esistono: un path
    inventato non deve mai passare silenziosamente.
    """
    group, _, field = path.partition(".")
    if group not in GROUP_OWNERS:
        raise ValueError(
            f"Gruppo sconosciuto '{group}' (validi: {sorted(GROUP_OWNERS)})"
        )
    if field:
        model = _GROUP_MODELS[group]
        head = field.split(".", 1)[0]
        if head not in model.model_fields:
            raise ValueError(
                f"Campo sconosciuto '{head}' nel gruppo '{group}' "
                f"(validi: {sorted(model.model_fields)})"
            )
    return GROUP_OWNERS[group]
