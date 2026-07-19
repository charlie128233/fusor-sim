"""Sezioni d'urto di fusione: parametrizzazione di Duane (NRL Plasma Formulary).

sigma(E) [barn] = (A5 + A2 / ((A4 - A3*E)^2 + 1)) / (E * (exp(A1/sqrt(E)) - 1))

con E = energia del proiettile nel laboratorio in keV (corretta per il
regime beam-target del fusore: ione veloce su gas neutro freddo).

D-D ha due rami (~50/50): D(d,n)He3 produce il neutrone, D(d,p)T no.
Li calcoliamo entrambi: il tasso di neutroni usa solo il ramo n.
"""

import numpy as np

from fusor_sim.contracts.run_config import GasSpecies

BARN_M2 = 1e-28
MEV_J = 1.602176634e-13

# coefficienti di Duane (A1..A5), E in keV, sigma in barn
_DUANE = {
    "DD_n": (47.88, 482.0, 3.08e-4, 1.177, 0.0),  # D(d,n)He3
    "DD_p": (46.097, 372.0, 4.36e-4, 1.22, 0.0),  # D(d,p)T
    "DT": (45.95, 50200.0, 1.368e-2, 1.076, 409.0),  # T(d,n)He4
}

# energia media liberata per reazione (D-D: media dei due rami)
ENERGY_PER_FUSION_J = {
    GasSpecies.DD: 3.65 * MEV_J,
    GasSpecies.DT: 17.59 * MEV_J,
}

_MIN_E_KEV = 0.2  # sotto: tunneling trascurabile, sigma = 0


def _duane_sigma_barn(coeffs: tuple, e_kev: np.ndarray) -> np.ndarray:
    a1, a2, a3, a4, a5 = coeffs
    e = np.asarray(e_kev, dtype=float)
    sigma = np.zeros_like(e)
    ok = e > _MIN_E_KEV
    if np.any(ok):
        ee = e[ok]
        with np.errstate(over="ignore"):
            gamow = np.exp(a1 / np.sqrt(ee)) - 1.0
            sigma[ok] = (a5 + a2 / ((a4 - a3 * ee) ** 2 + 1.0)) / (ee * gamow)
    return sigma


def cross_sections_m2(
    species: GasSpecies, e_kev: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """(sigma_totale, sigma_ramo_neutronico) in m^2, per energia in keV."""
    if species is GasSpecies.DD:
        s_n = _duane_sigma_barn(_DUANE["DD_n"], e_kev)
        s_p = _duane_sigma_barn(_DUANE["DD_p"], e_kev)
        return (s_n + s_p) * BARN_M2, s_n * BARN_M2
    s = _duane_sigma_barn(_DUANE["DT"], e_kev) * BARN_M2
    return s, s


# --------------------------------------------------------------------------
# Reattività termica <sigma*v> per plasmi maxwelliani (tokamak).
# Parametrizzazione di Bosch-Hale (Nucl. Fusion 32, 1992), D-T,
# valida per T tra 0.2 e 100 keV.

SIGMAV_DT_VALID_KEV = (0.2, 100.0)

_BH_DT_BG = 34.3827  # keV^(1/2)
_BH_DT_MRC2 = 1.124656e6  # keV
_BH_DT_C = (1.17302e-9, 1.51361e-2, 7.51886e-2, 4.60643e-3,
            1.35000e-2, -1.06750e-4, 1.36600e-5)


def sigmav_dt_m3_s(t_kev: float) -> float:
    """<sigma*v> D-T in m^3/s per temperatura ionica in keV.

    Fuori dal range di validità restituisce 0: chi chiama deve marcare
    il risultato come inaffidabile, non estrapolare in silenzio.
    """
    if not SIGMAV_DT_VALID_KEV[0] <= t_kev <= SIGMAV_DT_VALID_KEV[1]:
        return 0.0
    c1, c2, c3, c4, c5, c6, c7 = _BH_DT_C
    t = t_kev
    theta = t / (1.0 - (t * (c2 + t * (c4 + t * c6)))
                 / (1.0 + t * (c3 + t * (c5 + t * c7))))
    xi = (_BH_DT_BG**2 / (4.0 * theta)) ** (1.0 / 3.0)
    sv_cm3_s = c1 * theta * np.sqrt(xi / (_BH_DT_MRC2 * t**3)) * np.exp(-3.0 * xi)
    return float(sv_cm3_s) * 1e-6


E_DT_TOTAL_J = 17.59 * MEV_J  # energia per reazione D-T
E_DT_ALPHA_J = 3.52 * MEV_J  # frazione che resta nel plasma (particella alfa)
