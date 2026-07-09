# Lezione 5 — I muri della fisica: barriera coulombiana e Lawson

**Livello:** intermedio · **Obiettivo:** capire i due vincoli fondamentali che governano OGNI reattore a fusione, non solo il fusore.

## Muro 1: la barriera coulombiana

Due deutoni si respingono con forza crescente man mano che si
avvicinano. Classicamente servirebbero ~300 keV per toccarsi; per
fortuna la meccanica quantistica permette il tunneling, che rende la
fusione possibile già a decine di keV — ma con probabilità che crolla
esponenzialmente al calare dell'energia.

Il simulatore usa le sezioni d'urto vere (parametrizzazione di Duane,
NRL Plasma Formulary). Ordini di grandezza per D-D: a 10 keV ~10⁻⁴
barn, a 50 keV ~10⁻² barn, cento volte di più.

## Esperimento: D-D contro D-T

> 💬 passa al combustibile D-T e avvia

Confronta i neutroni/s col caso D-D a parità di tutto. La sezione
d'urto D-T è ~100 volte maggiore a queste energie (e ogni reazione
libera 17.6 MeV contro 3.65): per questo ogni progetto di reattore
serio usa D-T, nonostante il trizio sia radioattivo, raro e costoso.
Guarda anche la distanza da Lawson: è diminuita? Di quanto?

> 💬 torna al deuterio D-D

## Muro 2: il criterio di Lawson

Per il pareggio serve che il **triplo prodotto** n·T·τ (densità ×
temperatura × tempo di confinamento) superi una soglia:
~3×10²¹ keV·s/m³ per D-T, ~100 volte di più per D-D.

Il fusore ha la T (decine di keV, meglio di molti plasmi!) ma è
disastroso su n e τ: densità bassissima (gas a 0.5 Pa) e confinamento
di microsecondi (la vita di uno ione prima della griglia). Risultato:
13–16 ordini di grandezza sotto soglia. Non 13–16 *percento*: 13–16
*zeri*.

## Perché "ordini di grandezza" è la parola chiave

Migliorare un fattore 2, 10, persino 1000 non basta quando mancano
10¹⁴. È questo che distingue un problema di ingegneria (colmabile con
iterazioni) da un limite strutturale. I tokamak, che confinano con
campi magnetici senza oggetti materiali nel plasma, arrivano a ~1
ordine dalla soglia: ecco perché il mondo investe lì.

## Verifica la tua comprensione

1. Perché la fusione avviene anche sotto i 300 keV "classici"?
2. Perché D-T è il combustibile di ogni progetto serio, nonostante i
   suoi difetti?
3. Su quale delle tre grandezze di Lawson il fusore è forte, e su quali
   è perso?

> 💬 quanto manca al fusore per arrivare alla soglia di Lawson e perché?

Prossima lezione: la geometria — cosa succede se rompi la simmetria.
