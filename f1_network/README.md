# F1 Network Territoriale

Programma operativo del lunedì per costruire una rete locale di professionisti collegata a F1 Immobiliare.

## Regola vincolante

Comune/località dell'immobile = Comune/località del professionista. Non viene usato alcun fallback automatico verso comuni vicini.

Esempi:
- immobile a Condove -> professionisti di Condove;
- immobile a Bussoleno -> professionisti di Bussoleno.

## Posizionamento

F1 Immobiliare valorizza circa 30 anni di esperienza maturata nel territorio valsusino e nella prima cintura di Torino. Il primo contatto non chiede referral: serve a fissare un incontro di conoscenza e valutare una collaborazione reciproca.

## Categorie

- Geometra
- Architetto
- Amministratore condominio
- Notaio
- Avvocato
- Commercialista
- Consulente credito / finanziario
- Impresa edile

## Pipeline

DA_CONTATTARE -> CONTATTATO -> DA_RICHIAMARE -> APPUNTAMENTO -> INCONTRATO -> PARTNER_POTENZIALE -> RETE_F1

Sono disponibili anche DA_VERIFICARE e NON_INTERESSATO.

## Ciclo mensile

Il primo lunedì di ogni mese viene lavorata la coda dei professionisti che non hanno ancora aderito alla rete.

Regole:
- invio/contatto solo verso recapiti pubblici verificati;
- contatto via email e WhatsApp quando entrambi disponibili;
- chi passa a `RETE_F1` viene escluso automaticamente dal ciclo mensile di acquisizione;
- `NON_INTERESSATO` viene escluso;
- i partner aderenti vengono gestiti separatamente con comunicazioni dedicate alla collaborazione;
- la pagina operativa è `mensile.html`.

## Dati

`data/professionisti.csv` contiene il primo censimento pubblico del 16/08/2026.

`data/contatti_verificati.csv` contiene recapiti pubblici verificati e correzioni territoriali. Prima di ogni contatto vanno verificati attività, recapito e sede effettiva nel territorio indicato.

I territori vengono letti direttamente da `../seller_radar_auto/municipalities.csv`, così il Network segue la stessa lista operativa del radar F1.

Gli aggiornamenti di stato e le note effettuati dalla pagina sono salvati nel browser. A fine sessione usare `Esporta CSV aggiornato` come copia operativa.