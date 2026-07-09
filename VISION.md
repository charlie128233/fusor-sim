# Progetto: Simulatore didattico di fusione (fusore Farnsworth-Hirsch)

## Visione

Un simulatore divulgativo che permette a persone senza background tecnico di esplorare la fisica della fusione a confinamento elettrostatico (fusore), sperimentando via linguaggio naturale e imparando perché la fusione è difficile. L'LLM propone e interpreta; il simulatore giudica secondo le leggi fisiche vere. Obiettivo: avvicinare le persone alla fisica reale, incluso il rispetto per i suoi vincoli.

## Principio guida non negoziabile

Il simulatore è un giudice fisico onesto. È strutturalmente impossibile ottenere un falso "funziona": ogni risultato è accompagnato da un referto fisico obbligatorio. Meglio un modello semplice ma onesto di uno sofisticato ma compiacente.

## Gerarchia dei ruoli

- L'LLM propone configurazioni (anche insolite/creative) e interpreta i risultati. Mai oracolo fisico.
- Il simulatore giudica secondo leggi fisiche reali. È il verdetto.
- L'utente esplora e impara dai vincoli, non riceve risposte preconfezionate.

## Vincoli hardware

Target: singola GPU consumer (RTX 3080, 10 GB VRAM). Questo limita la scala: casi 2D/ridotti a risoluzione moderata. Nota tecnica: per il fusore la geometria sferica richiede 3D per una PIC valida (il 2D va bene solo per il campo di potenziale, non per una simulazione particellare corretta). Il tokamak invece è genuinamente 2D grazie alla simmetria assiale.

## Architettura a livelli

- **Interfaccia** (fuori dal loop di simulazione): chat/LLM, visualizzatore real-time (read-only), editor parametri. La chat comunica con l'orchestratore solo negli stati IDLE/PAUSED.
- **Orchestratore**: cuore di controllo. State machine IDLE → CONFIG → RUN → PAUSED → DONE. Valida ogni modifica parametrica contro vincoli fisici. Unico a emettere una nuova RunConfig, e solo fuori da RUN. Questo rende strutturalmente impossibile interagire col motore durante il loop caldo (è il "contratto dell'endpoint").
- **Router**: dato il problema, classifica e seleziona solver dal catalogo. Semplice per il fusore (un dominio), pronto a estendersi al tokamak.
- **RAG / Catalogo**: vector DB dei testi (il "libro delle formule", per spiegazioni) + catalogo di implementazioni validate. Il testo documenta; il codice eseguito viene solo dal catalogo, mai generato al volo.
- **Auto-tuner**: sceglie parametri numerici (passo temporale/CFL, precisione, block size) per massimizzare velocità sotto vincolo di stabilità. Gira in CONFIG.
- **Motore di simulazione** (loop caldo, chat disattivata): solver di campo → particle pusher (PIC) → diagnostica → referto. Unico blocco su GPU.
- **Stream/Storage**: buffer snapshot leggeri per il visualizzatore; checkpoint completi su HDF5 per pausa/ripresa.

## Contratti dati (la spina dorsale — definirli per primi)

### RunConfig (input al motore, immutabile durante un run)

- `geometry`: raggi griglie, raggio camera, trasparenza griglia, tipo geometria — da utente
- `physics`: tensione, specie gas (D-D/D-T), pressione, tasso sorgente ioni, temperatura — da utente
- `numerics`: risoluzione, n. particelle, dt, precisione, cuda_block_size — da auto-tuner
- `solver_selection`: id solver Poisson, id pusher — da router
- `run_control`: max_steps, snapshot_interval, checkpoint_interval, stop_conditions

Punto chiave: tre gruppi, tre proprietari diversi (utente / router / auto-tuner). Nessuno tocca il campo di un altro.

### SimState (output del motore)

- `meta`: step, sim_time, status, wall_clock
- `fields`: potenziale, campo E, densità di carica
- `particles`: posizioni, velocità, energie (sottocampionate per il viz, non tutte)
- `diagnostics`: tasso fusione, produzione neutroni, spettro energia ioni, perdite su griglia, efficienza ricircolo, bilancio potenza
- `health`: errore conservazione energia, numero CFL, warning numerici
- `physics_verdict` (obbligatorio, mai omesso): vedi sotto

Distinzione: snapshot leggeri ad alta frequenza (→ visualizzatore) vs checkpoint completi rari (→ disco).

### physics_verdict (il referto di onestà — il motore non restituisce mai risultato senza)

- `produces_fusion`: sì/no + tasso reazioni
- `net_energy_balance`: valore + segno (quasi sempre negativo)
- `loss_breakdown`: dove va l'energia (griglia, radiazione, fuga)
- `lawson_distance`: quanti ordini di grandezza dalla soglia di Lawson
- `numerical_reliability`: risultato affidabile o al limite?
- `honest_summary`: verdetto in linguaggio comprensibile

### ChatIntent (la chat non emette mai una RunConfig, solo patch validate dall'orchestratore)

- `action`: SET / SCALE / ADD_CONSTRAINT / QUERY / ADD_FORMULA_SOURCE
- `target`: path nella RunConfig
- `value`: nuovo valore o fattore
- `rationale`: opzionale, cosa cita dal RAG

## Controlli fisici obbligatori (i guardrail di onestà)

1. **Bilancio di potenza**: P_fusione − P_perdite, con scomposizione perdite (griglia = perdita dominante, radiazione, conduzione, fuga). Verdetto tipico: profondamente negativo.
2. **Criterio di Lawson**: densità × temperatura × tempo confinamento vs soglia. Mostrato su scala log. È il muro centrale.
3. **Barriera coulombiana / energia effettiva**: gli ioni raggiungono davvero l'energia di fusione? Distinguere caso ideale (bello, sbagliato) da perdite reali (thermalizzazione, neutri veloci).
4. **Conservazione energia numerica**: se il solver viola la conservazione oltre soglia → "risultato inaffidabile", non riportare il numero.
5. **Consistenza fisica di base**: range fisici, geometrie realizzabili, potenze finite.

## Estensioni future (già predisposte nell'architettura, da agganciare dopo)

- **Tokamak**: sostituire il solver Poisson elettrostatico con Grad-Shafranov (equilibrio magnetico). Stessa famiglia di equazioni ellittiche → scrivere il solver del fusore come risolutore ellittico generico rende il salto quasi indolore. Aggiungere geometria parametrica del toro.
- **Catalogo componenti reali** (fase costruttiva): vacuum_pumps, power_supplies, materials, detectors, gas_systems — ognuno impone vincoli reali sulla RunConfig e sul verdetto ("richiede 80 kV ma l'alimentatore arriva a 30 kV — non realizzabile"). Curato manualmente, non scraping in tempo reale. Include avvertenze di sicurezza.
- **Ponte hardware** (Fase 2-3): confronto simulazione vs dati reali registrati; poi eventuale monitoraggio/controllo. Sicurezza esplicita e prioritaria: alta tensione letale, raggi X, neutroni. Separare nettamente "guarda la simulazione" (per tutti) da "costruisci l'hardware" (per esperti con precauzioni).

## Roadmap di costruzione

1. Contratti dati (RunConfig, SimState, physics_verdict, ChatIntent) come schemi concreti — definirli per primi abilita lo sviluppo parallelo di ogni blocco.
2. Solver del campo: risolutore ellittico generico (Poisson sferico per il fusore, riusabile per Grad-Shafranov). Primo mattone: senza campo non c'è niente.
3. Particle pusher (PIC) + diagnostica + referto fisico.
4. Orchestratore + state machine.
5. Visualizzatore (consuma SimState).
6. Chat/LLM + RAG.
7. Estensioni: tokamak, catalogo componenti, ponte hardware.

## Note di sviluppo aperte (da decidere con lo sviluppatore)

- Stack preciso (solver GPU: es. CuPy/kernel CUDA; visualizzatore: PyVista/VTK/VisPy; vector DB per RAG; framework chat).
- CPU-first per chiarezza didattica, poi porting GPU — approccio consigliato.
- Ogni blocco è testabile in isolamento grazie ai contratti dati.
