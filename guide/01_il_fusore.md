# Lezione 1 — Anatomia del fusore

**Livello:** base · **Obiettivo:** capire come il fusore accelera gli ioni e lanciare la tua prima simulazione.

## Tre gusci concentrici

Guarda la scena 3D: vedi tre sfere una dentro l'altra.

- La **camera a vuoto** (esterna, grigia): contiene tutto; dentro c'è
  gas di deuterio a bassissima pressione (~0.5 Pa, un centomillesimo
  dell'atmosfera).
- L'**anodo** (blu): una griglia collegata a massa (0 V).
- Il **catodo** (rosso, al centro): una griglia di fili portata a
  tensione fortemente negativa, tipicamente −20/−80 kV.

## Il pozzo di potenziale

Tra anodo e catodo c'è una "cascata" elettrostatica. Quando una
molecola di gas viene ionizzata (perde un elettrone), lo ione positivo
D⁺ *cade* verso il catodo negativo, come un sasso in un pozzo. Cadendo
converte energia potenziale in energia cinetica: arrivato al centro con
−40 kV di tensione, ha ~40 keV di energia — proprio la scala che serve
per tentare la fusione.

La griglia catodica è quasi tutta vuota (trasparenza ~95%): la maggior
parte degli ioni la attraversa, converge al centro, e se non collide
riemerge dall'altra parte, risale la cascata, si ferma, e ricade.
Oscilla. È il **ricircolo**.

## Esperimento: la tua prima simulazione

> 💬 avvia la simulazione con i parametri di default

Mentre gira, osserva:

1. **La scena 3D**: i punti sono ioni (campione statistico). I colori
   indicano l'energia: verde = lento, giallo = medio, rosso = veloce.
   Nota che vicino al centro sono rossi: hanno finito la caduta.
2. **Il grafico del potenziale φ(r)**: il pozzo. Piatto dentro il
   catodo (gabbia di Faraday), ripido tra le griglie.
3. **Lo spettro di energia**: quanti ioni a quale energia. Perché non
   sono tutti alla stessa energia? Perché nascono a raggi diversi:
   chi nasce più in basso nel pozzo cade di meno.

## Verifica la tua comprensione

1. Perché il catodo deve essere negativo e non positivo?
2. Uno ione nato a metà del pozzo con quanta energia arriva al centro,
   rispetto a uno nato in cima?
3. Cosa vedi nel grafico del potenziale *dentro* il raggio del catodo,
   e perché?

> 💬 perché il potenziale è piatto dentro il catodo?

Prossima lezione: imparare a leggere il referto — il documento più
importante che il simulatore produce.
