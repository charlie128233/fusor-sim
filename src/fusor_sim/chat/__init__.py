"""Chat/LLM: l'interfaccia in linguaggio naturale.

L'LLM propone e interpreta, mai giudica: ogni proposta diventa un
ChatIntent che l'orchestratore valida, e ogni interpretazione è
accompagnata dal referto testuale del simulatore, mostrato sempre
integralmente all'utente.
"""

from fusor_sim.chat.llm_client import LLMClient
from fusor_sim.chat.pipeline import ChatOutcome, ChatPipeline

__all__ = ["ChatOutcome", "ChatPipeline", "LLMClient"]
