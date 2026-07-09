"""Router: dato il problema, seleziona i solver dal catalogo.

Oggi il dominio è uno solo (fusore sferico); la struttura esiste perché
l'estensione tokamak aggiungerà una geometria toroidale che mapperà su
un solver Grad-Shafranov, senza toccare orchestratore o motore.
"""

from fusor_sim.catalog import available_poisson_solvers, available_pushers
from fusor_sim.contracts.run_config import GeometryConfig, SolverSelection

_ROUTING_TABLE = {
    "spherical": SolverSelection(
        poisson_solver_id="poisson_spherical_fd_v1",
        pusher_id="leapfrog_radial_v1",
    ),
}


def geometry_class(geometry: GeometryConfig) -> str:
    """Classe geometrica per la selezione: concentrica o con catodo spostato."""
    return "spherical_concentric" if geometry.is_concentric else "spherical_offset"


def select_solvers(geometry: GeometryConfig) -> SolverSelection:
    if geometry.geometry_type not in _ROUTING_TABLE:
        raise ValueError(
            f"Nessun solver nel catalogo per la geometria "
            f"'{geometry.geometry_type}' (gestite: {sorted(_ROUTING_TABLE)})"
        )
    if not geometry.is_concentric:
        raise ValueError(
            "Geometria non concentrica (catodo spostato di "
            f"{geometry.cathode_offset_magnitude_m:.4g} m): nessun solver nel "
            "catalogo può GIUDICARE la fusione per questa configurazione. "
            "È disponibile l'anteprima del solo campo elettrostatico "
            "(field preview); riporta gli offset a 0 per simulare."
        )
    selection = _ROUTING_TABLE[geometry.geometry_type]
    # difesa in profondità: la tabella deve puntare a implementazioni validate
    assert selection.poisson_solver_id in available_poisson_solvers()
    assert selection.pusher_id in available_pushers()
    return selection
