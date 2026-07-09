# Lezione 7 — Onestà numerica: come un simulatore controlla se stesso

**Livello:** avanzato · **Obiettivo:** capire quando fidarsi di una simulazione — di questa e di qualunque altra.

## Una simulazione può sbagliare in silenzio

Un simulatore risolve equazioni a passi discreti: se il passo temporale
è troppo grande o la griglia troppo grossolana, i numeri escono
comunque — ma sono spazzatura. Il pericolo non è l'errore: è l'errore
*che sembra un risultato*.

## I due controlli di questo simulatore

1. **Conservazione dell'energia.** Nella fisica vera l'energia si
   conserva esattamente; nell'integrazione numerica quasi. Il motore
   misura a ogni passo lo scarto tra energia guadagnata dagli ioni e
   lavoro fatto dal campo. Se lo scarto cumulato supera il 2% →
   affidabilità "al limite"; oltre il 10% → "inaffidabile", e i numeri
   di fusione NON vengono riportati.
2. **CFL particellare.** Quanto si muove una particella in un passo,
   rispetto alla cella di griglia? Se attraversa più di una cella per
   passo, il campo che sente è campionato male.

Nel referto trovi entrambi. Questi controlli hanno già lavorato durante
lo sviluppo di questo stesso simulatore: la prima versione del motore
violava la conservazione del 26% e il referto la bocciò — il motore fu
corretto, non il referto.

## Esperimento: chi sceglie il passo temporale?

Nota che non puoi impostare il passo temporale dalla chat. Prova:

> 💬 imposta il passo temporale a 1e-8 secondi

Verrà rifiutato: i parametri numerici appartengono all'**auto-tuner**,
che li sceglie per massimizzare la velocità *sotto vincolo di
stabilità* — e verifica la scelta con un run di prova. È una divisione
dei poteri: tu decidi la fisica, il tuner decide i numeri, il motore
giudica.

## Cosa questo modello NON include (dichiarazione dei limiti)

La padronanza include sapere cosa manca. Questo motore è un modello
radiale 1D con momento angolare: onesto nel suo dominio, ma non
modella —

- **gli elettroni** (quindi niente radiazione di frenamento: le perdite
  reali sono maggiori di quelle riportate, e il referto lo dice);
- **lo scambio carica**: ione veloce + neutro fermo → neutro veloce che
  sfugge al campo (perdita importante nei fusori reali);
- **lo "star mode"**: i raggi luminosi attraverso i fori della griglia,
  che nascono da microcanali 3D che un modello radiale non può vedere;
- **scariche e rotture del vuoto**: la vera ingegneria del fusore.

## Verifica la tua comprensione

1. Perché "risultato inaffidabile → nessun numero" è meglio di
   "risultato inaffidabile → numero con asterisco"?
2. Perché il passo temporale non è un parametro dell'utente?
3. Il bilancio energetico riportato dal simulatore è ottimista o
   pessimista rispetto alla realtà, e perché?

> 💬 quali fenomeni fisici questo simulatore non modella?

Ultima lezione: oltre il fusore — cosa hai imparato che vale per tutta
la fusione.
