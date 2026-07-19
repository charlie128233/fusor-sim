"""Equilibrio di Grad-Shafranov per il tokamak (profili di Solov'ev).

L'equilibrio magnetico assisimmetrico di un tokamak è descritto da

    Delta* psi = R d/dR( (1/R) dpsi/dR ) + d^2 psi / dZ^2 = S(psi, R)

la stessa famiglia ellittica del Poisson del fusore: è il salto promesso
dal documento di visione. Con i profili di Solov'ev (p' e FF' costanti)
il termine sorgente diventa S = C1*R^2 + C2, l'equazione è lineare e ha
soluzioni analitiche esatte — le usiamo per validare il solver numerico
e per parametrizzare un equilibrio dalle grandezze macroscopiche
(raggio maggiore R0, raggio minore a, elongazione kappa).

Il numerico usa l'identità Delta*psi / R = div( grad(psi)/R ) e risolve
la forma auto-aggiunta -div( grad(psi)/R ) = -S/R con gradiente
coniugato matrix-free (stesso schema del Poisson 3D cartesiano),
Dirichlet dal profilo analitico sul bordo del dominio.

Limiti dichiarati: equilibrio idealizzato (profili di Solov'ev, statico,
in unità di flusso normalizzate) — descrive la FORMA delle superfici di
flusso; le potenze e il confinamento sono giudicati dal modello 0D.
"""

from dataclasses import dataclass

import numpy as np

from fusor_sim.contracts.tokamak import TokamakGeometryConfig


@dataclass(frozen=True)
class SolovevCoefficients:
    """psi = c1*(R^4/8 - R0^2*R^2/4 + R0^4/8) + c2*Z^2/2, con
    Delta* psi = c1*R^2 + c2. Asse magnetico in (R0, 0), psi(asse)=0."""

    c1: float
    c2: float
    r0: float

    def psi(self, r: np.ndarray, z: np.ndarray) -> np.ndarray:
        return (
            self.c1 * (r**4 / 8.0 - self.r0**2 * r**2 / 4.0 + self.r0**4 / 8.0)
            + self.c2 * z**2 / 2.0
        )

    def source(self, r: np.ndarray) -> np.ndarray:
        return self.c1 * r**2 + self.c2


def solovev_from_geometry(geometry: TokamakGeometryConfig) -> SolovevCoefficients:
    """Coefficienti che mettono l'asse in R0 e danno l'elongazione kappa.

    Vicino all'asse i contorni sono ellissi con rapporto Z/dR =
    sqrt(psi_RR/psi_ZZ) = kappa; flusso in unità normalizzate (c1=1).
    """
    c1 = 1.0
    c2 = c1 * geometry.major_radius_m**2 / geometry.elongation**2
    return SolovevCoefficients(c1=c1, c2=c2, r0=geometry.major_radius_m)


@dataclass(frozen=True)
class FluxMap:
    r_axis_m: np.ndarray
    z_axis_m: np.ndarray
    psi: np.ndarray  # (nR, nZ), unità normalizzate, 0 sull'asse magnetico
    psi_boundary: float  # valore di psi sull'ultima superficie chiusa (LCFS)
    magnetic_axis_r_m: float
    converged: bool
    residual_rel: float
    iterations: int


class GradShafranovSolver:
    """Solver validato del catalogo per l'equilibrio tokamak."""

    solver_id = "grad_shafranov_solovev_v1"
    supported_geometries = ("tokamak_axisymmetric",)

    def solve(
        self,
        geometry: TokamakGeometryConfig,
        n_nodes: int = 65,
        tol: float = 1e-9,
        max_iterations: int = 4000,
    ) -> FluxMap:
        coeffs = solovev_from_geometry(geometry)
        r0, a, kappa = (
            geometry.major_radius_m,
            geometry.minor_radius_m,
            geometry.elongation,
        )
        margin = 1.15
        r_ax = np.linspace(r0 - margin * a, r0 + margin * a, n_nodes)
        z_ax = np.linspace(-margin * kappa * a, margin * kappa * a, n_nodes)
        hr, hz = r_ax[1] - r_ax[0], z_ax[1] - z_ax[0]
        rr, zz = np.meshgrid(r_ax, z_ax, indexing="ij")

        boundary = np.zeros((n_nodes, n_nodes), dtype=bool)
        boundary[0, :] = boundary[-1, :] = True
        boundary[:, 0] = boundary[:, -1] = True
        free = ~boundary

        u_fixed = np.where(boundary, coeffs.psi(rr, zz), 0.0)

        # forma auto-aggiunta: -div( grad(psi)/R ) = -S/R
        r_half = (r_ax[:-1] + r_ax[1:]) / 2.0
        cr = (1.0 / r_half)[:, None]  # coefficiente sui semi-nodi in R
        cz = (1.0 / r_ax)[:, None]  # coefficiente (solo R) per i flussi in Z

        def div_grad(u: np.ndarray) -> np.ndarray:
            out = np.zeros_like(u)
            fr = cr * (u[1:, :] - u[:-1, :]) / hr**2
            out[:-1, :] += fr
            out[1:, :] -= fr
            fz = cz * (u[:, 1:] - u[:, :-1]) / hz**2
            out[:, :-1] += fz
            out[:, 1:] -= fz
            return out

        def apply_a(v: np.ndarray) -> np.ndarray:
            av = -div_grad(v)
            av[boundary] = 0.0
            return av

        b = div_grad(u_fixed) - coeffs.source(rr) / rr
        b[boundary] = 0.0

        v = np.zeros_like(u_fixed)
        r_res = b.copy()
        p = r_res.copy()
        rs = float((r_res * r_res).sum())
        rs0 = max(rs, 1e-300)
        iterations = 0
        for iterations in range(1, max_iterations + 1):
            ap = apply_a(p)
            alpha = rs / max(float((p * ap).sum()), 1e-300)
            v += alpha * p
            r_res -= alpha * ap
            rs_new = float((r_res * r_res).sum())
            if np.sqrt(rs_new / rs0) < tol:
                rs = rs_new
                break
            p = r_res + (rs_new / rs) * p
            rs = rs_new

        residual_rel = float(np.sqrt(rs / rs0))
        v[boundary] = 0.0
        psi = u_fixed + v

        i_axis = int(np.unravel_index(np.argmin(psi), psi.shape)[0])
        psi_boundary = float(coeffs.psi(np.array(r0 + a), np.array(0.0)))
        return FluxMap(
            r_axis_m=r_ax,
            z_axis_m=z_ax,
            psi=psi,
            psi_boundary=psi_boundary,
            magnetic_axis_r_m=float(r_ax[i_axis]),
            converged=residual_rel < tol * 10,
            residual_rel=residual_rel,
            iterations=iterations,
        )
