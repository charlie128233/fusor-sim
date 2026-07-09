# Lezione 8 — Oltre il fusore: la strada verso il pareggio

**Livello:** avanzato · **Obiettivo:** trasferire quello che hai imparato al quadro generale della fusione, e misurare la tua padronanza.

## Il bilancio del fusore, in una frase

Il fusore raggiunge le energie giuste (decine di keV — la temperatura
non è il suo problema!) ma confina con un oggetto materiale dentro il
plasma, e ogni oggetto materiale è un canale di perdita che nessuna
astuzia elimina. Densità bassa + confinamento di microsecondi =
13–16 ordini di grandezza da Lawson.

## Come fanno i tokamak

Il tokamak elimina l'oggetto materiale: confina il plasma con campi
magnetici a forma di ciambella (toro). Le particelle cariche spiraleggiano
lungo le linee di campo senza toccare nulla. Con volumi enormi e campi
intensi, i migliori esperimenti arrivano a ~1 ordine di grandezza dalla
soglia, e ITER punta a superarla (Q > 1 termico).

Il prezzo: complessità estrema — superconduttori, instabilità del
plasma, materiali che devono reggere flussi di neutroni da 14 MeV per
anni. La fusione magnetica ha trasformato un problema di *principio*
(il fusore non può) in un problema di *ingegneria titanica* (il tokamak
forse può).

Curiosità architetturale: l'equilibrio magnetico di un tokamak si
calcola con un'equazione (Grad-Shafranov) della stessa famiglia
matematica dell'equazione del campo che questo simulatore già risolve.
È il prossimo passo previsto di questo progetto.

## Le altre strade

- **Confinamento inerziale** (laser, NIF): comprimere una pallina di
  D-T così in fretta che fonde prima di espandersi. τ minuscolo,
  n gigantesca. Ha raggiunto l'ignizione scientifica nel 2022.
- **Varianti IEC senza griglia** (Polywell, POPS): tentativi di tenere
  l'idea del fusore eliminando i fili. Nessuna ha mai avvicinato il
  pareggio, ma il fusore resta un eccellente generatore di neutroni
  commerciale.

## Test di padronanza

Se sai rispondere a queste domande con numeri e meccanismi — non con
slogan — hai la padronanza che questa guida voleva darti:

1. Un amico dice: "ho letto di un ragazzo che ha costruito un reattore
   a fusione in garage". Cosa c'è di vero e cosa manca in quella frase?
2. Perché aumentare la corrente di ioni non avvicina il fusore al
   pareggio, ma aumentare la trasparenza della griglia sì (un po')?
3. Quale delle tre grandezze di Lawson il fusore soddisfa già, e con
   quale meccanismo?
4. Perché ogni progetto serio di reattore usa D-T e non D-D?
5. Cosa rende il tokamak fondamentalmente diverso dal fusore, sul piano
   delle perdite?
6. Una simulazione ti dà un risultato entusiasmante. Quali due domande
   fai prima di crederci? (Dominio di validità del modello; salute
   numerica del run.)

> 💬 fammi un quiz di 5 domande su tutto quello che ho imparato

## Dove andare da qui

Riprova gli esperimenti cambiando due parametri insieme; cerca la
configurazione col miglior rapporto fusione/perdite e chiediti perché
esiste comunque un tetto; e quando arriverà il modulo tokamak,
riconoscerai ogni concetto: Lawson, sezioni d'urto, perdite, onestà
numerica. Sono gli stessi ovunque. È questo il punto.
