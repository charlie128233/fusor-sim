"""Validazione del solver ellittico e del Poisson sferico contro
soluzioni analitiche note. Un solver entra nel catalogo solo se
riproduce la fisica esatta dove la fisica esatta è nota."""

import numpy as np
import pytest

from fusor_sim.catalog import (
    available_poisson_solvers,
    get_poisson_solver,
)
from fusor_sim.contracts.run_config import GeometryConfig, example_run_config
from fusor_sim.solvers.elliptic import (
    BoundaryCondition,
    EllipticProblem1D,
    solve_elliptic_1d,
)
from fusor_sim.solvers.poisson_spherical import EPSILON_0, PoissonSphericalSolver

R_CATHODE = 0.05
R_ANODE = 0.15
V_CATHODE = -40_000.0


def _analytic_vacuum(r: np.ndarray) -> np.ndarray:
    """Potenziale nel vuoto tra sfere concentriche: phi = A + B/r."""
    denom = 1.0 / R_CATHODE - 1.0 / R_ANODE
    return V_CATHODE * (1.0 / r - 1.0 / R_ANODE) / denom


def _vacuum_problem(n: int) -> EllipticProblem1D:
    r = np.linspace(R_CATHODE, R_ANODE, n)
    return EllipticProblem1D(
        x=r,
        weight=lambda s: s**2,
        flux_coeff=lambda s: s**2,
        rhs=np.zeros(n),
        left_bc=BoundaryCondition.dirichlet(V_CATHODE),
        right_bc=BoundaryCondition.dirichlet(0.0),
    )


# ------------------------------------------------------- solver generico


def test_cartesian_poisson_exact_on_parabola():
    """u'' = 2 con u(0)=0, u(1)=1 ha soluzione esatta u = x^2:
    le differenze finite del secondo ordine la riproducono a precisione macchina."""
    n = 51
    x = np.linspace(0.0, 1.0, n)
    problem = EllipticProblem1D(
        x=x,
        weight=lambda s: np.ones_like(s),
        flux_coeff=lambda s: np.ones_like(s),
        rhs=np.full(n, 2.0),
        left_bc=BoundaryCondition.dirichlet(0.0),
        right_bc=BoundaryCondition.dirichlet(1.0),
    )
    sol = solve_elliptic_1d(problem)
    assert sol.converged
    assert np.max(np.abs(sol.u - x**2)) < 1e-10


def test_spherical_vacuum_matches_analytic():
    sol = solve_elliptic_1d(_vacuum_problem(401))
    r = np.linspace(R_CATHODE, R_ANODE, 401)
    err = np.max(np.abs(sol.u - _analytic_vacuum(r))) / abs(V_CATHODE)
    assert err < 1e-4
    assert sol.converged


def test_spherical_vacuum_second_order_convergence():
    """Dimezzando h l'errore deve calare ~4x (schema del secondo ordine)."""
    errs = []
    for n in (101, 201, 401):
        r = np.linspace(R_CATHODE, R_ANODE, n)
        sol = solve_elliptic_1d(_vacuum_problem(n))
        errs.append(np.max(np.abs(sol.u - _analytic_vacuum(r))))
    order1 = np.log2(errs[0] / errs[1])
    order2 = np.log2(errs[1] / errs[2])
    assert order1 > 1.7
    assert order2 > 1.7


def test_uniform_charge_matches_analytic():
    """Con rho costante: phi = A + B/r - rho*r^2/(6*eps0), A e B dalle BC."""
    rho = 1e-6  # C/m^3
    n = 401
    r = np.linspace(R_CATHODE, R_ANODE, n)

    # coefficienti analitici dalle condizioni phi(r_c)=V_c, phi(r_a)=0
    part = lambda s: -rho * s**2 / (6.0 * EPSILON_0)
    m = np.array([[1.0, 1.0 / R_CATHODE], [1.0, 1.0 / R_ANODE]])
    q = np.array([V_CATHODE - part(R_CATHODE), -part(R_ANODE)])
    a_coef, b_coef = np.linalg.solve(m, q)
    analytic = a_coef + b_coef / r + part(r)

    problem = EllipticProblem1D(
        x=r,
        weight=lambda s: s**2,
        flux_coeff=lambda s: s**2,
        rhs=np.full(n, -rho / EPSILON_0),
        left_bc=BoundaryCondition.dirichlet(V_CATHODE),
        right_bc=BoundaryCondition.dirichlet(0.0),
    )
    sol = solve_elliptic_1d(problem)
    err = np.max(np.abs(sol.u - analytic)) / np.max(np.abs(analytic))
    assert err < 1e-4


def test_problem_validation():
    x = np.linspace(0.0, 1.0, 10)
    good = dict(
        weight=lambda s: np.ones_like(s),
        flux_coeff=lambda s: np.ones_like(s),
        rhs=np.zeros(10),
        left_bc=BoundaryCondition.dirichlet(0.0),
        right_bc=BoundaryCondition.dirichlet(0.0),
    )
    with pytest.raises(ValueError, match="uniforme"):
        EllipticProblem1D(x=x**2, **good)
    with pytest.raises(ValueError, match="rhs"):
        EllipticProblem1D(x=x, **{**good, "rhs": np.zeros(7)})
    with pytest.raises(ValueError, match="pinned"):
        EllipticProblem1D(x=x, **good, pinned={0: 5.0})


# --------------------------------------------------- solver del fusore


def _fusor_geometry() -> GeometryConfig:
    return GeometryConfig(
        chamber_radius_m=0.25,
        anode_radius_m=R_ANODE,
        cathode_radius_m=R_CATHODE,
        grid_transparency=0.95,
    )


def test_fusor_field_full_domain():
    """Dominio completo [0, anodo]: nucleo equipotenziale, profilo 1/r fuori."""
    # n scelto perché il catodo cada esattamente su un nodo (0.05 = 0.15/3)
    n = 301
    result = PoissonSphericalSolver().solve(
        _fusor_geometry(), cathode_voltage_v=V_CATHODE, n_points=n
    )

    assert result.snapped_cathode_radius_m == pytest.approx(R_CATHODE)
    assert result.numerics.converged

    # dentro il catodo: gabbia di Faraday, potenziale costante e campo nullo
    core_phi = result.phi_v[: result.cathode_node_index]
    assert np.max(np.abs(core_phi - V_CATHODE)) < 1e-6 * abs(V_CATHODE)
    core_e = result.e_r_v_per_m[: result.cathode_node_index - 1]
    assert np.max(np.abs(core_e)) < 1e-3 * abs(V_CATHODE) / R_ANODE

    # tra catodo e anodo: profilo analitico nel vuoto
    outside = slice(result.cathode_node_index, n)
    r_out = result.r_m[outside]
    err = np.max(np.abs(result.phi_v[outside] - _analytic_vacuum(r_out)))
    assert err / abs(V_CATHODE) < 1e-3

    # anodo a massa
    assert result.phi_v[-1] == 0.0


def test_fusor_field_direction_accelerates_ions():
    """Il campo tra catodo e anodo deve puntare verso il centro (E_r < 0):
    è ciò che accelera gli ioni positivi verso il nucleo."""
    result = PoissonSphericalSolver().solve(
        _fusor_geometry(), cathode_voltage_v=V_CATHODE, n_points=301
    )
    between = slice(result.cathode_node_index + 2, -2)
    assert np.all(result.e_r_v_per_m[between] < 0)


def test_insufficient_resolution_rejected():
    geo = GeometryConfig(
        chamber_radius_m=1.0,
        anode_radius_m=0.9,
        cathode_radius_m=0.001,
        grid_transparency=0.9,
    )
    with pytest.raises(ValueError, match="Risoluzione insufficiente"):
        PoissonSphericalSolver().solve(geo, cathode_voltage_v=-1000.0, n_points=32)


def test_charge_density_length_checked():
    with pytest.raises(ValueError, match="Densità di carica"):
        PoissonSphericalSolver().solve(
            _fusor_geometry(),
            cathode_voltage_v=V_CATHODE,
            n_points=301,
            charge_density_c_per_m3=np.zeros(100),
        )


# ------------------------------------------------------------- catalogo


def test_catalog_resolves_example_config_solver():
    cfg = example_run_config()
    solver = get_poisson_solver(cfg.solver_selection.poisson_solver_id)
    assert isinstance(solver, PoissonSphericalSolver)


def test_catalog_rejects_unknown_solver():
    with pytest.raises(KeyError, match="non nel catalogo"):
        get_poisson_solver("poisson_llm_generated_v99")


def test_catalog_lists_validated_solvers():
    assert available_poisson_solvers() == ["poisson_spherical_fd_v1"]
