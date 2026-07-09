# I parametri del simulatore e i loro effetti

Parametri modificabili dall'utente (gruppi geometry e physics):

- **physics.cathode_voltage_v** (negativa, fino a -500000 V): più
  tensione = ioni più energetici = sezione d'urto più alta = più
  neutroni. Ma anche più potenza immessa e persa sulla griglia.
  I fusori amatoriali reali stanno tra -20000 e -50000 V.
- **physics.pressure_pa** (1e-4 - 100 Pa): più gas = più bersagli per
  la fusione beam-target, ma anche più collisioni che degradano il
  fascio. I fusori operano tipicamente a 0.1-1 Pa.
- **physics.gas_species**: "D-D" (deuterio, accessibile) o "D-T"
  (col trizio: sezione d'urto ~100x, ma il trizio è radioattivo e
  quasi introvabile).
- **physics.ion_source_rate_per_s**: quanti ioni nascono al secondo
  (dipende dalla sorgente di ionizzazione). Più ioni = più corrente =
  più neutroni E più potenza persa, proporzionalmente: il rapporto
  guadagno/perdita non migliora.
- **geometry.cathode_radius_m** e **anode_radius_m**: griglia interna
  ed esterna. Catodo piccolo = campo più concentrato al centro.
- **geometry.grid_transparency** (0-1): frazione aperta della griglia.
  Il parametro più importante per le perdite: la vita media di uno
  ione in attraversamenti è 1/(1-T).
- **geometry.cathode_offset_x_m / _y_m / _z_m**: spostamento del catodo
  dal centro. Rompe la simmetria sferica: la configurazione resta
  realizzabile e il campo elettrostatico 3D si può calcolare e vedere
  (anteprima "solo campo"), ma NESSUN solver del catalogo attuale può
  giudicare la fusione per una geometria non concentrica. Il simulatore
  lo dichiara invece di inventare numeri: è il suo principio di onestà.

Parametri NON modificabili dalla chat: il gruppo numerics (passo
temporale, risoluzione...) appartiene all'auto-tuner, il gruppo
solver_selection al router. Chiedere di cambiarli verrà rifiutato.
