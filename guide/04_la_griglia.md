# Lezione 4 — La griglia: il difetto strutturale

**Livello:** intermedio · **Obiettivo:** capire perché la griglia catodica condanna il fusore, quantitativamente.

## Un conto che chiunque può fare

La griglia ha trasparenza T: a ogni attraversamento, uno ione
sopravvive con probabilità T. La vita media di uno ione, misurata in
attraversamenti, è 1/(1−T):

- T = 0.90 → ~10 attraversamenti
- T = 0.95 → ~20 attraversamenti
- T = 0.98 → ~50 attraversamenti

Ogni ione intercettato scarica TUTTA la sua energia (decine di keV) sui
fili. Ecco perché nel referto la griglia domina le perdite.

## Esperimento: la trasparenza

> 💬 porta la trasparenza della griglia a 0.90 e avvia

Poi:

> 💬 porta la trasparenza a 0.98 e avvia

Confronta: efficienza di ricircolo (dovrebbe seguire la trasparenza),
potenza persa sulla griglia, neutroni/s. Con più ricircolo ogni ione
fa più passaggi al centro → più occasioni di fusione per ione: il
rapporto migliora davvero. È uno dei pochi parametri che lo fa
(ricordi la domanda della Lezione 3?).

## La trappola

Allora perché non fare una griglia con T = 0.999? Perché una griglia è
fatta di fili veri: più è trasparente, più i fili sono sottili e
radi — e meno definiscono il campo elettrico, meno reggono il calore
(decine di watt concentrati su grammi di tungsteno), meno tengono la
tensione. I fusori reali si fermano intorno a T ≈ 0.92–0.98.

Questo è il vicolo cieco: **per confinare meglio servirebbe più
griglia, per perdere meno ne servirebbe meno.** Le varianti che
provano a eliminare la griglia (Polywell, griglie virtuali di
elettroni) scambiano questo problema con altri, finora senza pareggio.

## Esperimento mentale + verifica

> 💬 con trasparenza 0.95, dopo quanti attraversamenti sopravvive metà degli ioni?

1. Se T = 0.95, che frazione di ioni sopravvive a 14 attraversamenti?
   (0.95¹⁴ ≈ 0.49: metà.)
2. Perché una griglia più trasparente migliora il rapporto
   fusione/perdite mentre più tensione no... anzi sì? (Rifletti: la
   tensione aumenta la sezione d'urto *per passaggio*; la trasparenza
   aumenta i *passaggi*. Entrambe migliorano il rapporto — ma nessuna
   delle due basta a colmare 14 ordini di grandezza.)
3. Dove finisce fisicamente l'energia degli ioni intercettati?

Prossima lezione: i due muri fondamentali — barriera coulombiana e
criterio di Lawson.
