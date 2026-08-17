# F1 Network Territoriale

Programma operativo del lunedì per costruire una rete locale di professionisti collegata a F1 Immobiliare.

## Regola territoriale

Comune dell'immobile = Comune del professionista. Nessun fallback automatico verso comuni vicini.

Esempi:
- immobile a Condove -> professionisti di Condove;
- immobile a Bussoleno -> professionisti di Bussoleno.

Eccezioni amministrative registrate nel manifest:
- Novaretto -> Comune di Caprie;
- San Valeriano -> Comune di Borgone Susa.

Le frazioni restano visibili come territori F1, ma la rete professionale viene ricercata nel Comune amministrativo di appartenenza.

## Posizionamento

F1 Immobiliare valorizza circa 30 anni di esperienza maturata nel territorio valsusino e nella prima cintura di Torino. Il primo contatto serve a fissare un incontro di conoscenza e valutare una collaborazione reciproca; non viene presentato come richiesta immediata di referral.

## Pipeline

DA_CONTATTARE -> CONTATTATO -> DA_RICHIAMARE -> APPUNTAMENTO -> INCONTRATO -> PARTNER_POTENZIALE -> RETE_F1 / ADERITO

Sono disponibili anche DA_VERIFICARE e NON_INTERESSATO.

## Regole di contatto

Il fatto che un recapito sia pubblicato online non abilita automaticamente comunicazioni promozionali.

La dashboard registra separatamente:
- stato commerciale;
- verifica del canale telefonico (`DA_VERIFICARE`, `RPO_OK`, `CONSENSO_TELEFONO`, `NON_CONTATTABILE`);
- consenso al follow-up digitale (`NO_CONSENSO`, `CONSENSO_DIGITALE`).

WhatsApp ed email di follow-up vengono abilitati solo quando è registrato `CONSENSO_DIGITALE`.

## Ciclo mensile

Il primo lunedì di ogni mese si lavora la coda di follow-up autorizzata.

Sono inclusi solo contatti con `CONSENSO_DIGITALE` e sono esclusi automaticamente:
- RETE_F1;
- ADERITO;
- NON_INTERESSATO.

La pagina operativa è `mensile.html`.

## Dati e manifest

`data/professionisti.csv` contiene il censimento iniziale.

I recapiti verificati e le successive integrazioni sono divisi in batch CSV. `data/contact_manifest.json` elenca i batch caricati dalla dashboard e contiene anche gli alias territoriali. In questo modo nuovi blocchi di contatti possono essere aggiunti senza riscrivere il programma.

I territori F1 vengono letti da `../seller_radar_auto/municipalities.csv`.

Gli stati operativi, le note, la verifica telefonica e il consenso digitale sono salvati nel browser. A fine sessione usare `Esporta CSV` come copia operativa.