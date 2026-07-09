"""Orchestratore: il cuore di controllo del simulatore.

State machine IDLE -> CONFIG -> RUN -> PAUSED -> DONE. È l'unico attore
che emette una RunConfig, e solo fuori da RUN: la chat non può toccare
il motore durante il loop caldo per costruzione, non per convenzione.
"""

from fusor_sim.orchestrator.autotuner import tune_numerics
from fusor_sim.orchestrator.core import (
    IntentResult,
    Orchestrator,
    OrchestratorState,
    StateError,
)
from fusor_sim.orchestrator.router import select_solvers

__all__ = [
    "IntentResult",
    "Orchestrator",
    "OrchestratorState",
    "StateError",
    "select_solvers",
    "tune_numerics",
]
