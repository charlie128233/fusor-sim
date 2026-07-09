# Lezione 6 — Geometria e campo: rompere la simmetria

**Livello:** avanzato · **Obiettivo:** capire perché la simmetria sferica è essenziale, e come il simulatore gestisce onestamente ciò che non sa giudicare.

## La simmetria è il progetto

Il fusore funziona perché tutte le traiettorie convergono nello stesso
punto: il centro. È la simmetria sferica a garantirlo — il campo spinge
ogni ione esattamente verso il centro, da qualunque direzione cada. Se
sposti il catodo, il fuoco si sfalda: gli ioni convergono male, la
densità centrale crolla, e con lei le collisioni.

## Esperimento: sposta il catodo

Clicca il catodo (la sfera rossa) nella scena 3D e trascinalo, oppure:

> 💬 sposta il catodo di 3 cm lungo x

Osserva cosa succede: compare il badge **⚠ NON GIUDICABILE**. Il
simulatore ti sta dicendo una cosa precisa: *questa configurazione è
costruibile, ma nessun modello nel mio catalogo sa calcolarne la
fusione*. Il motore attuale assume la simmetria sferica; usarlo su una
geometria asimmetrica produrrebbe numeri privi di senso. Un simulatore
disonesto te li darebbe lo stesso.

## Esperimento: guarda comunque il campo

> 💬 mostrami il campo elettrico in 3D

Il campo elettrostatico, da solo, si PUÒ calcolare per qualunque
geometria (equazione di Poisson in 3D). Il piano colorato nella scena
mostra il pozzo di potenziale: nota come si deforma attorno al catodo
spostato — il fuoco non è più al centro della camera. Il referto ora
dice "solo campo": niente numeri di fusione, perché nessuna dinamica
particellare è stata calcolata. Vedi la fisica che c'è, non ricevi
quella che non è stata calcolata.

## Perché questa distinzione è importante

Nella scienza computazionale il peccato capitale è usare un modello
fuori dal suo dominio di validità. Il simulatore codifica il dominio di
validità nei suoi contratti: il router sa quali geometrie ogni solver
copre, e rifiuta il resto *spiegando perché*. Quando un giorno esisterà
un motore PIC 3D completo, queste geometrie diventeranno giudicabili —
lo stesso principio, con un catalogo più ricco.

## Esperimento di chiusura

> 💬 riporta il catodo al centro e avvia la simulazione

Il badge sparisce, il run parte: sei tornato nel dominio giudicabile.

## Verifica la tua comprensione

1. Perché la convergenza degli ioni richiede la simmetria sferica?
2. Che differenza c'è tra "configurazione non realizzabile" e
   "configurazione non giudicabile"? (Prova: chiedi un catodo più
   grande dell'anodo, e confronta il tipo di rifiuto.)
3. Perché il campo si può calcolare anche quando la fusione no?

Prossima lezione: l'onestà numerica — come un simulatore controlla
se stesso.
