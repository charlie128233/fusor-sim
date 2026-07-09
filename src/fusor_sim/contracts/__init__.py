"""Contratti dati: la spina dorsale del simulatore.

Ogni blocco (solver, orchestratore, chat, visualizzatore) comunica SOLO
attraverso questi schemi. Le regole di onestà sono codificate qui in modo
strutturale, non lasciate alla buona volontà dei chiamanti.
"""

from fusor_sim.contracts.chat_intent import ChatAction, ChatIntent
from fusor_sim.contracts.field_preview import FieldPreview
from fusor_sim.contracts.ownership import Owner, owner_of
from fusor_sim.contracts.physics_verdict import (
    LossBreakdown,
    NumericalReliability,
    PhysicsVerdict,
)
from fusor_sim.contracts.run_config import (
    GasSpecies,
    GeometryConfig,
    NumericsConfig,
    PhysicsConfig,
    RunConfig,
    RunControl,
    SolverSelection,
    StopCondition,
)
from fusor_sim.contracts.sim_state import (
    Diagnostics,
    FieldSnapshot,
    Health,
    ParticleSample,
    RunStatus,
    SimMeta,
    SimState,
)

__all__ = [
    "ChatAction",
    "ChatIntent",
    "Diagnostics",
    "FieldPreview",
    "FieldSnapshot",
    "GasSpecies",
    "GeometryConfig",
    "Health",
    "LossBreakdown",
    "NumericalReliability",
    "NumericsConfig",
    "Owner",
    "owner_of",
    "ParticleSample",
    "PhysicsConfig",
    "PhysicsVerdict",
    "RunConfig",
    "RunControl",
    "RunStatus",
    "SimMeta",
    "SimState",
    "SolverSelection",
    "StopCondition",
]
