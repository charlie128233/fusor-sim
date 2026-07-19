"""Catalogo di implementazioni validate.

Regola del progetto: il codice eseguito dal motore viene SOLO da qui,
mai generato al volo. Il router sceglie per id; un id sconosciuto è un
errore esplicito, non un fallback silenzioso.
"""

from fusor_sim.solvers.grad_shafranov import GradShafranovSolver
from fusor_sim.solvers.poisson_cartesian3d import PoissonCartesian3DSolver
from fusor_sim.solvers.poisson_spherical import PoissonSphericalSolver

_POISSON_SOLVERS: dict[str, type] = {
    PoissonSphericalSolver.solver_id: PoissonSphericalSolver,
}

# solver di solo campo (anteprima): non giudicano la fusione
_FIELD_SOLVERS: dict[str, type] = {
    PoissonCartesian3DSolver.solver_id: PoissonCartesian3DSolver,
}

# solver di equilibrio magnetico (tokamak)
_EQUILIBRIUM_SOLVERS: dict[str, type] = {
    GradShafranovSolver.solver_id: GradShafranovSolver,
}

def _pushers() -> dict[str, type]:
    # import pigro: i motori usano il catalogo per risolvere i solver,
    # un import a livello di modulo creerebbe un ciclo
    from fusor_sim.engine.simulation import RadialPICEngine
    from fusor_sim.engine.tokamak import Tokamak0DEngine

    return {
        RadialPICEngine.pusher_id: RadialPICEngine,
        Tokamak0DEngine.engine_id: Tokamak0DEngine,
    }


def get_poisson_solver(solver_id: str) -> PoissonSphericalSolver:
    if solver_id not in _POISSON_SOLVERS:
        raise KeyError(
            f"Solver Poisson '{solver_id}' non nel catalogo "
            f"(validi: {sorted(_POISSON_SOLVERS)})"
        )
    return _POISSON_SOLVERS[solver_id]()


def get_field_solver(solver_id: str) -> PoissonCartesian3DSolver:
    if solver_id not in _FIELD_SOLVERS:
        raise KeyError(
            f"Solver di campo '{solver_id}' non nel catalogo "
            f"(validi: {sorted(_FIELD_SOLVERS)})"
        )
    return _FIELD_SOLVERS[solver_id]()


def get_equilibrium_solver(solver_id: str) -> GradShafranovSolver:
    if solver_id not in _EQUILIBRIUM_SOLVERS:
        raise KeyError(
            f"Solver di equilibrio '{solver_id}' non nel catalogo "
            f"(validi: {sorted(_EQUILIBRIUM_SOLVERS)})"
        )
    return _EQUILIBRIUM_SOLVERS[solver_id]()


def get_pusher_class(pusher_id: str) -> type:
    pushers = _pushers()
    if pusher_id not in pushers:
        raise KeyError(
            f"Pusher '{pusher_id}' non nel catalogo (validi: {sorted(pushers)})"
        )
    return pushers[pusher_id]


def available_poisson_solvers() -> list[str]:
    return sorted(_POISSON_SOLVERS)


def available_pushers() -> list[str]:
    return sorted(_pushers())
