"""Poisson elettrostatico per il fusore in simmetria sferica.

Equazione:  (1/r^2) d/dr( r^2 dphi/dr ) = -rho / epsilon_0

Dominio [0, raggio anodo]:
- r = 0: flusso nullo (simmetria);
- r = raggio anodo: Dirichlet a 0 V (anodo a massa);
- r = raggio catodo: elettrodo immerso, nodo pinned alla tensione catodica.

Modello e sue approssimazioni (dichiarate, non nascoste):
- la griglia catodica è trattata come sfera equipotenziale perfetta:
  per il CAMPO è l'approssimazione standard; la trasparenza della griglia
  entra nel PIC (intercettazione delle particelle), non qui;
- il raggio del catodo viene agganciato al nodo di griglia più vicino
  ("snap"): il raggio effettivo usato è riportato nel risultato.
"""

from dataclasses import dataclass

import numpy as np

from fusor_sim.contracts.run_config import GeometryConfig
from fusor_sim.solvers.elliptic import (
    BoundaryCondition,
    EllipticProblem1D,
    EllipticSolution,
    solve_elliptic_1d,
)

EPSILON_0 = 8.8541878128e-12  # F/m


@dataclass(frozen=True)
class RadialPotential:
    """Campo radiale risolto, con referto numerico del solver."""

    r_m: np.ndarray
    phi_v: np.ndarray
    e_r_v_per_m: np.ndarray  # E_r = -dphi/dr
    cathode_node_index: int
    snapped_cathode_radius_m: float  # raggio catodo effettivo dopo lo snap
    numerics: EllipticSolution


class PoissonSphericalSolver:
    """Solver validato del catalogo: Poisson sferico a differenze finite."""

    solver_id = "poisson_spherical_fd_v1"
    supported_geometries = ("spherical_concentric",)

    def solve(
        self,
        geometry: GeometryConfig,
        cathode_voltage_v: float,
        n_points: int = 512,
        charge_density_c_per_m3: np.ndarray | None = None,
    ) -> RadialPotential:
        """Risolve il potenziale su [0, raggio anodo].

        charge_density_c_per_m3: densità di carica ai nodi radiali
        (stessa lunghezza della griglia), None = vuoto.
        """
        r_anode = geometry.anode_radius_m
        r = np.linspace(0.0, r_anode, n_points)
        h = r[1] - r[0]

        idx_cathode = round(geometry.cathode_radius_m / h)
        if not 1 <= idx_cathode <= n_points - 2:
            raise ValueError(
                f"Risoluzione insufficiente: con {n_points} punti il catodo "
                f"(r={geometry.cathode_radius_m} m) non cade su un nodo interno"
            )

        if charge_density_c_per_m3 is None:
            rho = np.zeros(n_points)
        else:
            rho = np.asarray(charge_density_c_per_m3, dtype=float)
            if len(rho) != n_points:
                raise ValueError(
                    f"Densità di carica su {len(rho)} nodi, griglia di {n_points}"
                )

        problem = EllipticProblem1D(
            x=r,
            weight=lambda s: s**2,
            flux_coeff=lambda s: s**2,
            rhs=-rho / EPSILON_0,
            left_bc=BoundaryCondition.zero_flux(),
            right_bc=BoundaryCondition.dirichlet(0.0),
            pinned={idx_cathode: cathode_voltage_v},
        )
        solution = solve_elliptic_1d(problem)

        return RadialPotential(
            r_m=r,
            phi_v=solution.u,
            e_r_v_per_m=-np.gradient(solution.u, r),
            cathode_node_index=idx_cathode,
            snapped_cathode_radius_m=float(r[idx_cathode]),
            numerics=solution,
        )
