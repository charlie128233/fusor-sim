# La barriera coulombiana e le sezioni d'urto

Due nuclei si respingono elettrostaticamente: per fondere devono
avvicinarsi a ~femtometri, superando (per effetto tunnel) la barriera
coulombiana di centinaia di keV. La probabilità di tunneling cresce
ripidissimamente con l'energia: la sezione d'urto D-D a 10 keV è
~1000 volte più piccola che a 50 keV.

## Nel fusore: beam-target

Nel fusore la fusione è quasi tutta "beam-target": uno ione veloce
(accelerato dal potenziale) colpisce una molecola di gas neutro ferma.
Il tasso per ione è n_gas * sigma(E) * v. Le sezioni d'urto usate dal
simulatore sono la parametrizzazione di Duane (NRL Plasma Formulary).

D-D ha due rami circa equiprobabili: D(d,n)He3 produce un neutrone da
2.45 MeV (quello che si misura), D(d,p)T produce un protone e trizio.
Energia media liberata: 3.65 MeV per reazione. D-T produce un neutrone
da 14.1 MeV e libera 17.6 MeV, con sezione d'urto ~100 volte maggiore
di D-D a parità di energia: per questo è il combustibile dei reattori.

## L'inganno del caso ideale

Se ogni ione arrivasse al centro con l'intera energia q*V e restasse
lì per sempre, i numeri sembrerebbero migliori. In realtà: scambio
carica con i neutri (lo ione veloce diventa neutro veloce e se ne va),
termalizzazione, e la griglia. Il simulatore modella la caduta reale
nel potenziale autoconsistente, non il caso ideale.
