"""Gestione macro-particelle del PIC radiale: iniezione e deposizione di carica.

Le particelle nascono per ionizzazione del gas tra le griglie: posizione
uniforme nel volume, velocità termica alla temperatura del gas (è il campo
a dare loro l'energia, cadendo nel pozzo di potenziale). Ogni macro-particella
rappresenta `macro_weight` ioni reali.
"""

import numpy as np

K_B = 1.380649e-23  # J/K
Q_E = 1.602176634e-19  # C
M_D = 3.3435837768e-27  # kg, deutone


def sample_injection(
    rng: np.random.Generator,
    k: int,
    r_min: float,
    r_max: float,
    temperature_k: float,
    mass_kg: float = M_D,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """k nuove particelle: (r, v_r, L) con L = m * r * v_tangenziale."""
    u = rng.random(k)
    r = (r_min**3 + u * (r_max**3 - r_min**3)) ** (1.0 / 3.0)  # uniforme nel volume
    sigma = np.sqrt(K_B * temperature_k / mass_kg)
    v_r = rng.normal(0.0, sigma, k)
    v_t = sigma * np.sqrt(-2.0 * np.log1p(-rng.random(k)))  # Rayleigh (2 gradi tangenziali)
    ang_mom = mass_kg * r * v_t
    return r, v_r, ang_mom


def shell_volumes(n_nodes: int, h: float) -> np.ndarray:
    """Volume del guscio sferico associato a ogni nodo radiale."""
    r = np.arange(n_nodes) * h
    lo = np.clip(r - h / 2.0, 0.0, None)
    hi = r + h / 2.0
    hi[-1] = r[-1]  # l'ultimo nodo è il bordo del dominio
    return (4.0 * np.pi / 3.0) * (hi**3 - lo**3)


def deposit_charge(
    r: np.ndarray,
    macro_weight: float,
    h: float,
    volumes: np.ndarray,
    charge: float = Q_E,
) -> np.ndarray:
    """Densità di carica ai nodi radiali, pesatura CIC (cloud-in-cell) lineare."""
    n_nodes = len(volumes)
    counts = np.zeros(n_nodes)
    if r.size:
        x = r / h
        i0 = np.minimum(x.astype(int), n_nodes - 2)
        frac = x - i0
        np.add.at(counts, i0, 1.0 - frac)
        np.add.at(counts, i0 + 1, frac)
    return charge * macro_weight * counts / volumes
