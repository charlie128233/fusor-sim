# Lezione 2 — Leggere il referto

**Livello:** base · **Obiettivo:** saper interpretare ogni voce del referto fisico, il verdetto che accompagna ogni simulazione.

## Il referto non si può togliere

Il simulatore è costruito in modo che nessun risultato esista senza il
suo referto: è strutturale, non una cortesia. Il referto risponde a
cinque domande, sempre le stesse.

## Le cinque voci

1. **Produce fusione?** Sì/no e il tasso di reazioni al secondo. Un
   fusore a −40 kV produce davvero ~10⁵ reazioni/s: fusione autentica.
2. **Bilancio energetico netto**: potenza recuperata dalla fusione meno
   potenza persa. Guarda i due numeri: decine di watt immessi, decine
   di *nano*watt recuperati. Il rapporto è ~10⁻⁹: per ogni watt
   investito ne torna un miliardesimo.
3. **Dove va l'energia (perdite)**: nel fusore la voce dominante è
   sempre la **griglia catodica** — gli ioni che colpiscono i fili.
4. **Distanza da Lawson**: quanti ordini di grandezza mancano alla
   soglia di pareggio. Un fusore tipico: 13–16 ordini. Non è un difetto
   di ingegneria: è la struttura del confinamento elettrostatico.
5. **Affidabilità numerica**: il simulatore controlla se stesso
   (conservazione dell'energia, passo temporale). Se un run non è
   affidabile, i numeri di fusione *non vengono riportati affatto*.

## Esperimento: leggi un referto per intero

> 💬 avvia la simulazione

A run finito, leggi il referto in basso e verifica di saper rispondere:

- Quanti neutroni al secondo? (È il numero che un fusore reale
  *misura*: i neutroni attraversano tutto e si contano con rivelatori.)
- Qual è il rapporto tra potenza immessa e recuperata?
- Che percentuale delle perdite è dovuta alla griglia?
- Il run era affidabile? Con che errore di conservazione dell'energia?

> 💬 spiegami il referto voce per voce

## Il ricircolo

Tra i grafici c'è anche l'**efficienza di ricircolo**: la frazione di
attraversamenti della griglia che sopravvivono. Confrontala con la
trasparenza della griglia (0.95 di default): dovrebbero coincidere.
Capirai perché nella Lezione 4.

## Verifica la tua comprensione

1. Perché "produce fusione = sì" non significa "funziona"?
2. Se il referto dice "risultato inaffidabile", cosa è successo e cosa
   NON devi fare con i numeri?
3. Che ordine di grandezza ha il rapporto guadagno/spesa di un fusore?

Prossima lezione: mettere le mani sui parametri e costruire intuizione
sperimentale.
