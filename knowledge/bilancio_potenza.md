# Il bilancio di potenza

Il verdetto energetico è P_netta = P_fusione - P_perdite. In ogni
fusore mai costruito o simulato onestamente, il segno è profondamente
negativo: si immettono decine di watt (o kilowatt) e si recuperano
frazioni di microwatt in fusione. Rapporti tipici: 1e-8 - 1e-10.

## Dove va l'energia

1. **Griglia catodica** (dominante): ogni ione intercettato deposita
   la sua energia cinetica sui fili. Nel simulatore è la voce grid_w.
2. **Radiazione** (bremsstrahlung): gli elettroni che frenano nel campo
   dei nuclei emettono raggi X. Il simulatore attuale NON la modella
   (niente elettroni): il bilancio reale è quindi ancora peggiore di
   quello riportato, e il referto lo dichiara.
3. **Fuga**: particelle veloci che raggiungono la parete.
4. **Scambio carica**: ione veloce + neutro fermo -> neutro veloce
   (che il campo non trattiene) + ione fermo. Non ancora modellato.

## Perché "produce fusione" non significa "funziona"

Un fusore amatoriale produce davvero 1e4-1e6 neutroni al secondo: è
fusione autentica, misurabile. Ma 1e5 reazioni D-D al secondo sono
~6e-8 W recuperati contro ~30 W immessi. Il fusore è un eccellente
generatore di neutroni da laboratorio e un pessimo reattore.
