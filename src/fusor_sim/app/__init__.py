"""App web: visualizzatore real-time (read-only) + chat, sopra l'orchestratore.

L'interfaccia sta FUORI dal loop di simulazione: legge SimState dal
buffer snapshot e parla con l'orchestratore, mai col motore.
"""
