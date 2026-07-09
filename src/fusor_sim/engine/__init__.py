"""Motore di simulazione: il loop caldo (campo -> pusher -> diagnostica -> referto).

Modello di questo primo motore, dichiarato apertamente:
PIC radiale 1D a simmetria sferica. Ogni macro-particella è uno ione D+
con stato (r, v_r, L): il momento angolare L è conservato esattamente
(forza centrale) e il moto tangenziale entra come barriera centrifuga.
È un modello ridotto — la PIC 3D completa è un'estensione futura — ma
la sua fisica è onesta: campo autoconsistente, sezioni d'urto reali,
bilancio energetico misurato, e ogni risultato passa dal referto.
"""

from fusor_sim.engine.simulation import RadialPICEngine

__all__ = ["RadialPICEngine"]
