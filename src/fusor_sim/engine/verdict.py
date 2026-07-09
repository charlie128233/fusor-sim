"""Costruzione del PhysicsVerdict: il punto in cui il motore emette il giudizio.

Le regole quantitative vivono qui; le regole strutturali (un verdetto
inaffidabile non può riportare numeri, ecc.) vivono nel contratto e
vengono ri-verificate alla costruzione dell'oggetto.
"""

import math

from fusor_sim.contracts.physics_verdict import (
    LossBreakdown,
    NumericalReliability,
    PhysicsVerdict,
)
from fusor_sim.contracts.run_config import GasSpecies
from fusor_sim.contracts.sim_state import Health
from fusor_sim.engine.fusion import ENERGY_PER_FUSION_J

# Soglie (approssimate, scopo didattico) del triplo prodotto di Lawson
# n*T*tau in keV*s/m^3. D-D è ~2 ordini di grandezza più difficile di D-T.
LAWSON_THRESHOLD_KEV_S_M3 = {
    GasSpecies.DT: 3e21,
    GasSpecies.DD: 1e23,
}

# soglie di affidabilità numerica
_ENERGY_ERR_RELIABLE = 0.02
_ENERGY_ERR_MARGINAL = 0.10
_CFL_RELIABLE = 1.0
_CFL_MARGINAL = 2.0


def assess_reliability(health: Health) -> NumericalReliability:
    err, cfl = health.energy_conservation_error, health.cfl_number
    if err < _ENERGY_ERR_RELIABLE and cfl <= _CFL_RELIABLE:
        return NumericalReliability.RELIABLE
    if err < _ENERGY_ERR_MARGINAL and cfl <= _CFL_MARGINAL:
        return NumericalReliability.MARGINAL
    return NumericalReliability.UNRELIABLE


def build_verdict(
    *,
    gas_species: GasSpecies,
    fusion_rate_per_s: float,
    neutron_rate_per_s: float,
    input_power_w: float,
    grid_loss_w: float,
    escape_loss_w: float,
    lawson_triple_kev_s_m3: float,
    health: Health,
) -> PhysicsVerdict:
    reliability = assess_reliability(health)
    losses = LossBreakdown(
        grid_w=grid_loss_w,
        radiation_w=0.0,  # elettroni non modellati: perdita reale > 0, dichiarato
        conduction_w=0.0,
        escape_w=escape_loss_w,
    )

    if reliability is NumericalReliability.UNRELIABLE:
        return PhysicsVerdict(
            numerical_reliability=reliability,
            produces_fusion=None,
            fusion_rate_per_s=None,
            fusion_power_w=None,
            input_power_w=input_power_w,
            net_energy_balance_w=None,
            loss_breakdown=losses,
            lawson_distance_orders=None,
            honest_summary=(
                "RISULTATO NON AFFIDABILE: la simulazione viola la conservazione "
                f"dell'energia (errore {health.energy_conservation_error:.1%}, "
                f"CFL {health.cfl_number:.2g}) e nessun numero di fusione viene "
                "riportato. Servono un passo temporale più piccolo o una griglia "
                "più fine, non un'interpretazione ottimistica."
            ),
        )

    fusion_power_w = fusion_rate_per_s * ENERGY_PER_FUSION_J[gas_species]
    net_w = fusion_power_w - losses.total_w
    threshold = LAWSON_THRESHOLD_KEV_S_M3[gas_species]
    orders = math.log10(threshold / max(lawson_triple_kev_s_m3, 1e-30))

    dominant_pct = 100.0 * grid_loss_w / losses.total_w if losses.total_w > 0 else 0.0
    produces = fusion_rate_per_s > 0

    summary = (
        f"Fusione: {'sì' if produces else 'no'} "
        f"({fusion_rate_per_s:.3g} reazioni/s, {neutron_rate_per_s:.3g} neutroni/s). "
        f"Bilancio energetico: {net_w:+.3g} W — potenza immessa {input_power_w:.3g} W, "
        f"recuperata dalla fusione {fusion_power_w:.3g} W. "
        f"Perdita dominante: griglia catodica ({dominant_pct:.0f}% delle perdite). "
        f"Distanza dalla soglia di Lawson: {orders:.1f} ordini di grandezza. "
        "Non modellati: radiazione ed elettroni, quindi il bilancio reale è "
        "ancora peggiore di così."
    )
    if reliability is NumericalReliability.MARGINAL:
        summary += (
            " AVVERTENZA: affidabilità numerica al limite "
            f"(errore energia {health.energy_conservation_error:.1%}): "
            "prendere i numeri come ordini di grandezza."
        )

    return PhysicsVerdict(
        numerical_reliability=reliability,
        produces_fusion=produces,
        fusion_rate_per_s=fusion_rate_per_s,
        fusion_power_w=fusion_power_w,
        input_power_w=input_power_w,
        net_energy_balance_w=net_w,
        loss_breakdown=losses,
        lawson_distance_orders=orders,
        honest_summary=summary,
    )
