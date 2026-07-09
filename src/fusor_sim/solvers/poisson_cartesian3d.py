"""Poisson elettrostatico 3D cartesiano con elettrodi sferici immersi.

Serve l'anteprima "solo campo" per geometrie che il modello radiale non
copre (catodo fuori centro). Nel vuoto: laplaciano(phi) = 0 con
- nodi fuori dalla sfera dell'anodo: fissati a 0 V (anodo a massa);
- nodi dentro la sfera del catodo (eventualmente spostata): fissati a V_c.

È lo stesso trucco dell'elettrodo immerso usato nel solver radiale
(nodi "pinned"), esteso al 3D. Il sistema, simmetrico e definito
positivo, è risolto con gradiente coniugato matrix-free. Il residuo
raggiunto è parte del risultato: se non converge, lo si dichiara.

Limite dichiarato: le superfici sferiche sono approssimate a gradini
sulla griglia cartesiana (errore O(h) vicino agli elettrodi).
"""

from dataclasses import dataclass

import numpy as np

from fusor_sim.contracts.run_config import GeometryConfig


@dataclass(frozen=True)
class Field3D:
    axis_m: np.ndarray  # coordinate dei nodi (uguali sui tre assi)
    potential_v: np.ndarray  # (n, n, n)
    converged: bool
    residual_rel: float
    iterations: int


def _laplacian(u: np.ndarray) -> np.ndarray:
    """Laplaciano discreto a 7 punti (in unità di h^2)."""
    lap = -6.0 * u
    lap[1:, :, :] += u[:-1, :, :]
    lap[:-1, :, :] += u[1:, :, :]
    lap[:, 1:, :] += u[:, :-1, :]
    lap[:, :-1, :] += u[:, 1:, :]
    lap[:, :, 1:] += u[:, :, :-1]
    lap[:, :, :-1] += u[:, :, 1:]
    return lap


class PoissonCartesian3DSolver:
    """Solver validato del catalogo per l'anteprima di campo."""

    solver_id = "poisson_cartesian3d_fd_v1"
    supported_geometries = ("spherical_concentric", "spherical_offset")

    def solve(
        self,
        geometry: GeometryConfig,
        cathode_voltage_v: float,
        n_nodes: int = 64,
        tol: float = 1e-8,
        max_iterations: int = 2000,
    ) -> Field3D:
        ra, rc = geometry.anode_radius_m, geometry.cathode_radius_m
        offset = np.array(
            [
                geometry.cathode_offset_x_m,
                geometry.cathode_offset_y_m,
                geometry.cathode_offset_z_m,
            ]
        )
        axis = np.linspace(-ra, ra, n_nodes)
        x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")

        outside_anode = x**2 + y**2 + z**2 >= ra**2
        inside_cathode = (
            (x - offset[0]) ** 2 + (y - offset[1]) ** 2 + (z - offset[2]) ** 2
        ) <= rc**2
        fixed = outside_anode | inside_cathode
        free = ~fixed
        if not np.any(free):
            raise ValueError("Risoluzione insufficiente: nessun nodo libero tra gli elettrodi")

        u_fixed = np.where(inside_cathode, float(cathode_voltage_v), 0.0)

        # CG su A v = b, con A = -laplaciano ristretto ai nodi liberi
        # e b = laplaciano del campo dei vincoli (v = 0 sui nodi fissati)
        def apply_a(v: np.ndarray) -> np.ndarray:
            av = -_laplacian(v)
            av[fixed] = 0.0
            return av

        b = _laplacian(u_fixed)
        b[fixed] = 0.0

        v = np.zeros_like(u_fixed)
        r = b.copy()
        p = r.copy()
        rs = float((r * r).sum())
        rs0 = max(rs, 1e-300)
        iterations = 0
        for iterations in range(1, max_iterations + 1):
            ap = apply_a(p)
            alpha = rs / max(float((p * ap).sum()), 1e-300)
            v += alpha * p
            r -= alpha * ap
            rs_new = float((r * r).sum())
            if np.sqrt(rs_new / rs0) < tol:
                rs = rs_new
                break
            p = r + (rs_new / rs) * p
            rs = rs_new

        residual_rel = float(np.sqrt(rs / rs0))
        v[fixed] = 0.0
        return Field3D(
            axis_m=axis,
            potential_v=u_fixed + v,
            converged=residual_rel < tol * 10,
            residual_rel=residual_rel,
            iterations=iterations,
        )
