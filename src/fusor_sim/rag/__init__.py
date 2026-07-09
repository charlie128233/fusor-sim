"""RAG: il "libro delle formule".

Il testo documenta e spiega; il codice eseguito viene SOLO dal catalogo.
Questo modulo recupera passaggi dai testi curati in knowledge/ per dare
all'LLM fonti da citare — mai formule da eseguire.
"""

from fusor_sim.rag.retriever import KnowledgeBase, Passage

__all__ = ["KnowledgeBase", "Passage"]
