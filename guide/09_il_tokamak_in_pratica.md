# Lezione 9 — Il tokamak in pratica

**Livello:** avanzato · **Obiettivo:** usare il modulo tokamak per toccare con mano perché il confinamento magnetico è la strada dei reattori — e cosa costa.

## Un motore diverso, lo stesso giudice

Passa al dominio tokamak:

> 💬 passa al tokamak

Il simulatore ora usa due modelli, dichiarati nel referto: l'**equilibrio
di Grad-Shafranov** (la stessa famiglia di equazioni ellittiche del campo
del fusore!) per la forma delle superfici di flusso, e un **bilancio di
potenza 0D** con il confinamento dallo scaling empirico IPB98(y,2) — lo
stesso tipo di modello usato negli studi di sistema dei reattori veri.

## Esperimento: la macchina di partenza

> 💬 avvia la simulazione

Osserva: la temperatura sale (il riscaldamento ausiliario e le particelle
alfa scaldano il plasma), poi si stabilizza dove le perdite pareggiano.
Leggi il referto: nota **Q** (potenza di fusione / potenza ausiliaria) e
soprattutto la voce perdite: trasporto e radiazione — e **zero griglia**.
Non c'è nessun oggetto materiale nel plasma: è il vantaggio strutturale
che il fusore non può avere.

La macchina di default è di media taglia: produce megawatt di fusione ma
Q < 1. La distanza da Lawson non si misura più in 14 ordini di
grandezza: siamo a meno di uno.

## Esperimento: la corsa al pareggio

Prova a superare Q = 1 (breakeven). Le leve vere, in ordine di potenza
nello scaling: dimensione (τ_E ~ R²), corrente di plasma (τ_E ~ I^0.93),
campo, densità.

> 💬 porta il raggio maggiore a 3 metri e avvia

> 💬 porta la corrente di plasma a 10 MA e il campo a 8 tesla e avvia

Quando superi Q = 1, fermati un momento: hai appena visto il pareggio
scientifico — quello per cui si costruisce ITER (R0 = 6.2 m, 15 MA,
obiettivo Q = 10). Prova anche i suoi parametri:

> 💬 configura un tokamak come ITER: raggio maggiore 6.2 m, raggio minore 2 m, elongazione 1.7, campo 5.3 T, corrente 15 MA, densità 10, riscaldamento 50 MW, e avvia

## L'altra faccia: perché non è finita

Q > 1 nel modello 0D non è una centrale elettrica: il referto elenca
cosa manca (profili radiali, impurità, limiti di densità e pressione,
disruzioni), e restano i muri ingegneristici — materiali che reggano
i neutroni da 14 MeV, trizio da produrre, superconduttori. Il modello
ti mostra la fisica del pareggio, non la sua ingegneria.

## Verifica la tua comprensione

1. Perché nel referto del tokamak la perdita "griglia" è zero, e quale
   voce prende il suo posto?
2. Quale parametro pesa di più nel tempo di confinamento, e perché
   questo spiega le dimensioni di ITER?
3. Che differenza c'è tra il Q di questo modello e "produrre energia
   elettrica netta"?

> 💬 confronta il referto del tokamak con quello del fusore: cosa è cambiato e cosa no?

Se sai rispondere collegando i numeri dei referti alle formule delle
lezioni precedenti, il percorso è completo: hai gli strumenti per
leggere criticamente qualunque notizia sulla fusione.
