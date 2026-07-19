# fusor-sim

Simulatore didattico di fusione a confinamento elettrostatico (fusore Farnsworth-Hirsch).
Visione completa e architettura: [VISION.md](VISION.md).

## Stato

- [x] **1. Contratti dati** — `RunConfig`, `SimState`, `PhysicsVerdict`, `ChatIntent` (`src/fusor_sim/contracts/`)
- [x] **2. Solver del campo** — risolutore ellittico generico 1D auto-aggiunto + Poisson sferico con elettrodo immerso (`src/fusor_sim/solvers/`), catalogo solver validati (`src/fusor_sim/catalog/`)
- [x] **3. Motore PIC + diagnostica + referto** — PIC radiale sferico con drift libero esatto, sezioni d'urto D-D/D-T (Duane, NRL), bilancio energetico misurato, `PhysicsVerdict` generato a ogni snapshot (`src/fusor_sim/engine/`)
- [x] **4. Orchestratore + state machine** — IDLE → CONFIG → RUN → PAUSED → DONE, gating strutturale della chat, router, auto-tuner con probe empirico, vincoli espliciti (`src/fusor_sim/orchestrator/`)
- [x] **5. Visualizzatore** — app web (FastAPI + Plotly): potenziale, spettro ioni, serie temporali, referto con affidabilità (`src/fusor_sim/app/`)
- [x] **6. Chat/LLM + RAG** — pipeline linguaggio naturale → ChatIntent validati, endpoint LLM OpenAI-compatible, libro delle formule con retrieval BM25 (`src/fusor_sim/chat/`, `src/fusor_sim/rag/`, `knowledge/`)
- [x] **6c. Guida didattica** — percorso in 9 lezioni (base → padronanza) in `guide/`: teoria, esperimenti guidati cliccabili che precompilano la chat, domande di verifica e test di padronanza; indicizzata dal RAG (l'LLM fa da tutor e cita le lezioni), avanzamento salvato in locale, scheda «Guida» nella UI
- [x] **6b. Scena 3D interattiva** — viewer/editor Three.js: componenti cliccabili, slider e drag del catodo (stesso percorso intent validato della chat), particelle come ricostruzione isotropa dichiarata. Offset del catodo nei contratti: la geometria non concentrica è **realizzabile ma non giudicabile** (il router lo dichiara) e ha l'**anteprima "solo campo"** — Poisson 3D cartesiano a elettrodi immersi (CG matrix-free), referto con scope `field_only` strutturalmente privo di numeri di fusione

- [x] **7a. Tokamak** — secondo dominio completo: equilibrio 2D **Grad-Shafranov**
  (profili di Solov'ev, CG matrix-free, validato ESATTAMENTE contro la soluzione
  analitica) + motore dinamico **0D a bilancio di potenza** (reattività Bosch-Hale,
  riscaldamento alfa, bremsstrahlung, confinamento da scaling IPB98(y,2), errore
  d'integrazione misurato) — stesso `PhysicsVerdict`, con zero perdite su griglia
  e distanza da Lawson in ordini ~1 invece di ~15. Selettore di dominio nella UI,
  superfici di flusso, T(t), potenze e Q(t); lezione 9 nella guida.
  Non modellati (dichiarato nel referto): profili radiali, impurità, limiti
  operativi (Greenwald, beta), disruzioni.

Estensioni future: catalogo componenti reali (i vincoli espliciti sono già il
gancio), ponte hardware, PIC 3D per geometrie fusore non concentriche.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

## Avvio

```bash
.venv/Scripts/python -m uvicorn fusor_sim.app.server:app --port 8001
# poi apri http://127.0.0.1:8001
```

La chat usa un endpoint LLM OpenAI-compatible, configurabile via ambiente:
`FUSOR_LLM_BASE` (default `http://127.0.0.1:8000/v1`) e `FUSOR_LLM_MODEL`
(default: il primo modello esposto da `/models`). Senza LLM l'app resta
pienamente usabile dai controlli manuali.

## Principio non negoziabile

Il simulatore è un giudice fisico onesto, e l'onestà è **strutturale**, non una convenzione:

- un `SimState` senza `physics_verdict` non è costruibile (campo obbligatorio senza default);
- un verdetto `unreliable` con numeri di fusione riportati viene rifiutato dal validatore;
- `produces_fusion` deve coincidere con `fusion_rate_per_s > 0`;
- la chat può proporre modifiche (`ChatIntent`) solo su campi di proprietà dell'utente
  (`geometry`, `physics`): un SET su `numerics.dt_s` non è nemmeno rappresentabile;
- ogni `RunConfig` è frozen: si sostituisce, non si muta.
