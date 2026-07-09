"""Risolutore ellittico generico 1D in forma auto-aggiunta.

Equazione risolta:  (1/w(x)) * d/dx( g(x) * du/dx ) = f(x)

La stessa forma copre l'intera famiglia che interessa al progetto:
- Poisson sferico a simmetria radiale:  w = g = r^2   (fusore)
- Poisson cilindrico radiale:           w = g = r
- Poisson cartesiano:                   w = g = 1
- Grad-Shafranov (tokamak, futuro): stessa forma in 2D (R,Z) con
  g = 1/R — la versione 2D adotterà questa identica interfaccia.

Caratteristiche pensate per il fusore:
- nodi "pinned": vincoli di Dirichlet su nodi interni, per rappresentare
  elettrodi immersi nel dominio (la griglia catodica);
- condizione di Neumann a flusso nullo, per la simmetria in r = 0;
- ogni soluzione riporta il residuo ottenuto: l'affidabilità numerica
  è parte del risultato, mai sottintesa.

Discretizzazione: volumi finiti ai nodi, coefficienti di flusso ai
semi-nodi, secondo ordine. Sistema tridiagonale risolto con l'algoritmo
di Thomas (diretto, O(n)).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class BCType(str, Enum):
    DIRICHLET = "dirichlet"
    NEUMANN_ZERO_FLUX = "neumann_zero_flux"


@dataclass(frozen=True)
class BoundaryCondition:
    kind: BCType
    value: float = 0.0  # usato solo per Dirichlet

    @staticmethod
    def dirichlet(value: float) -> "BoundaryCondition":
        return BoundaryCondition(BCType.DIRICHLET, value)

    @staticmethod
    def zero_flux() -> "BoundaryCondition":
        return BoundaryCondition(BCType.NEUMANN_ZERO_FLUX)


@dataclass(frozen=True)
class EllipticProblem1D:
    """Problema (1/w) d/dx(g du/dx) = f su griglia uniforme crescente."""

    x: np.ndarray
    weight: Callable[[np.ndarray], np.ndarray]  # w(x), valutata dove serve
    flux_coeff: Callable[[np.ndarray], np.ndarray]  # g(x)
    rhs: np.ndarray  # f ai nodi
    left_bc: BoundaryCondition
    right_bc: BoundaryCondition
    pinned: dict[int, float] = field(default_factory=dict)  # nodo interno -> valore

    def __post_init__(self) -> None:
        n = len(self.x)
        if n < 3:
            raise ValueError("Servono almeno 3 nodi")
        h = np.diff(self.x)
        if not np.allclose(h, h[0], rtol=1e-10) or h[0] <= 0:
            raise ValueError("La griglia deve essere uniforme e crescente")
        if len(self.rhs) != n:
            raise ValueError(f"rhs ha {len(self.rhs)} valori, la griglia {n} nodi")
        for idx in self.pinned:
            if not 0 < idx < n - 1:
                raise ValueError(
                    f"Nodo pinned {idx} non interno: i bordi si fissano con le BC"
                )


@dataclass(frozen=True)
class EllipticSolution:
    """Soluzione + referto numerico: il residuo è parte del risultato."""

    u: np.ndarray
    residual_rel: float
    converged: bool
    method: str
    n_points: int


_RESIDUAL_TOL = 1e-10


def _thomas(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> np.ndarray:
    """Algoritmo di Thomas per sistemi tridiagonali (a=sub, b=diag, c=super)."""
    n = len(d)
    cp = np.empty(n)
    dp = np.empty(n)
    cp[0] = c[0] / b[0]
    dp[0] = d[0] / b[0]
    for i in range(1, n):
        m = b[i] - a[i] * cp[i - 1]
        cp[i] = c[i] / m
        dp[i] = (d[i] - a[i] * dp[i - 1]) / m
    u = np.empty(n)
    u[-1] = dp[-1]
    for i in range(n - 2, -1, -1):
        u[i] = dp[i] - cp[i] * u[i + 1]
    return u


def solve_elliptic_1d(problem: EllipticProblem1D) -> EllipticSolution:
    x = problem.x
    n = len(x)
    h = float(x[1] - x[0])

    x_half = (x[:-1] + x[1:]) / 2.0
    g_half = np.asarray(problem.flux_coeff(x_half), dtype=float)
    w = np.asarray(problem.weight(x), dtype=float)

    a = np.zeros(n)
    b = np.zeros(n)
    c = np.zeros(n)
    d = np.asarray(problem.rhs, dtype=float).copy()

    # nodi interni: bilancio di flusso in forma conservativa
    a[1:-1] = g_half[:-1] / (w[1:-1] * h * h)
    c[1:-1] = g_half[1:] / (w[1:-1] * h * h)
    b[1:-1] = -(a[1:-1] + c[1:-1])

    # bordo sinistro
    if problem.left_bc.kind is BCType.DIRICHLET:
        b[0], c[0], d[0] = 1.0, 0.0, problem.left_bc.value
    else:  # flusso nullo: volume finito sulla semi-cella [x0, x0 + h/2]
        w_cell = float(problem.weight(x[0] + h / 4.0)) * (h / 2.0)
        c[0] = g_half[0] / (h * w_cell)
        b[0] = -c[0]

    # bordo destro
    if problem.right_bc.kind is BCType.DIRICHLET:
        b[-1], a[-1], d[-1] = 1.0, 0.0, problem.right_bc.value
    else:
        w_cell = float(problem.weight(x[-1] - h / 4.0)) * (h / 2.0)
        a[-1] = g_half[-1] / (h * w_cell)
        b[-1] = -a[-1]

    # elettrodi immersi: righe identità sui nodi pinned
    for idx, value in problem.pinned.items():
        a[idx], b[idx], c[idx], d[idx] = 0.0, 1.0, 0.0, value

    u = _thomas(a, b, c, d)

    # errore all'indietro normwise: ||Au - d|| / (||A||*||u|| + ||d||).
    # È la misura standard di affidabilità di un solve diretto: insensibile
    # al cattivo condizionamento apparente delle righe ~1/h^2.
    au = b * u
    au[1:] += a[1:] * u[:-1]
    au[:-1] += c[:-1] * u[1:]
    norm_a = float(np.max(np.abs(a) + np.abs(b) + np.abs(c)))
    scale = norm_a * float(np.max(np.abs(u))) + float(np.max(np.abs(d)))
    residual_rel = float(np.max(np.abs(au - d)) / (scale + np.finfo(float).tiny))

    return EllipticSolution(
        u=u,
        residual_rel=residual_rel,
        converged=residual_rel < _RESIDUAL_TOL,
        method="finite_volume_thomas_direct",
        n_points=n,
    )
