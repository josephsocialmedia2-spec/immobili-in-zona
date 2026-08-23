# F1 Seller Radar AUTO

Radar automatico di opportunità immobiliari pubbliche per F1 Immobiliare. Il sistema esegue discovery, scoring, cross-match, Area Radar, prepara il giro di acquisizione e può inviare le nuove opportunità via email/WhatsApp quando le relative credenziali sono configurate.

## STANDARD OPERATIVO OUTPUT RADAR

Da questo momento ogni risultato operativo destinato al giro di acquisizione deve indicare sempre, nell'ordine:

1. COMUNE
2. VIA
3. NUMERO CIVICO
4. COSA CERCARE SUL POSTO
5. PREZZO ATTUALE
6. EVENTUALE PREZZO PRECEDENTE E VARIAZIONE
7. SELLER SIGNAL
8. SCORE 0-100
9. FONTE / DOMAIN
10. URL
11. AZIONE: VAI IN ZONA oppure APRI FONTE E VERIFICA INDIRIZZO

Formato minimo obbligatorio:

COMUNE: [comune]
INDIRIZZO: [via] [numero civico]
COSA CERCARE: [tipo immobile / cartello / stabile / riferimento utile]
PREZZO: [euro]
SEGNALE: [se disponibile]
SCORE: [0-100]
FONTE: [portale/domain]
URL: [link]
AZIONE: [VAI IN ZONA / APRI FONTE E VERIFICA INDIRIZZO]

Regole:
- Non inventare mai il numero civico. Se non è pubblicato, scrivere: CIVICO DA VERIFICARE.
- Non inventare mai il prezzo. Se non è disponibile, scrivere: PREZZO DA VERIFICARE.
- Dare priorità ai risultati con indirizzo completo e verificabile.
- L'output deve essere immediatamente utilizzabile sul territorio: deve rispondere alla domanda **DOVE VADO, COSA CERCO, QUANTO COSTA**.
- Ordinare i risultati per priorità commerciale e, quando possibile, per percorso geografico efficiente.
- Applicare retention mobile di 365 giorni.
- Evitare duplicati tra portali.
- Non aggirare CAPTCHA, login, verifiche umane o protezioni anti-bot.

## DUE BINARI OPERATIVI

Gli annunci non vengono più scartati solo perché pubblicati da un'agenzia.

- `LEAD_DIRETTO` = annuncio con indizio privato. Può generare `VAI IN ZONA` e, solo dopo verifica della fonte e del gate RPO, anche `CHIAMA`.
- `AREA_OPPORTUNITY` = annuncio con indizio agenzia. Non è un privato e non va contato come tale, ma se contiene un indirizzo utile genera `VAI IN ZONA` per presidiare via/stabile e cercare ulteriori seller signal territoriali.
- `AREA_DA_VERIFICARE` = natura dell'inserzionista non determinata. L'indirizzo può essere usato come segnale territoriale finché la fonte non viene verificata.

Regola fondamentale: il telefono di Tecnocasa, Gabetti, Tempocasa o di qualunque altra agenzia non deve essere trattato come telefono del proprietario. Un annuncio di agenzia vale come **segnale di zona**, non come contatto diretto del venditore.

## QUALITY GATE CSV

Il file `validate_radar_csv.py` deve essere usato per ripulire gli export del radar prima dell'import nel CRM.

Controlli principali:
- scarta pagine categoria/ricerca e mantiene separati gli annunci dettaglio;
- marca gli annunci di agenzia per evitare falsi `PRIVATO`;
- scarta risultati fuori territorio, aste e risultati non operativi;
- normalizza i prezzi legacy espressi in migliaia;
- pulisce il campo indirizzo quando contiene testo estraneo;
- valida esclusivamente telefoni già presenti nell'export, senza eseguire scraping di nuovi contatti;
- scarta la P.IVA di Subito `05526340962` / `5526340962`, che può essere erroneamente catturata dal footer come se fosse un telefono;
- marca come sospetti i numeri ripetuti su molti risultati non correlati.

Esempio:

`python validate_radar_csv.py radar_SUSA.csv -o radar_SUSA_PULITO.csv`

Il quality gate non raccoglie nuovi dati personali, non interroga endpoint nascosti e non aggira protezioni dei portali.

## OUTPUT GENERATI

- `data/work_queue.csv` — coda completa del radar, arricchita con `TIPO_OPPORTUNITA`, `MOTIVO_AREA`, `VIA_RADAR`, `INDIRIZZI_ZONA`, `AZIONE_ZONA`.
- `data/giro_acquisizione.csv` — lista operativa ordinata per score.
- `data/area_radar.csv` — indirizzi pubblicamente rilevati, tipo opportunità e azioni territoriali.
- `data/state.json` — storico degli annunci monitorati.
- `dashboard.html` — dashboard pubblica.

## AUTOMAZIONE

GitHub Actions esegue il radar ogni giorno alle **02:00 ora italiana** e può essere avviato manualmente. Al termine invia a `f1immobiliaresusa@gmail.com` un file Excel `.xlsx` completo, con priorità, indirizzi, prezzi, ribassi, contatti pubblici già presenti nei risultati e link cliccabili.

Flusso: discovery per comune → merge → scoring → cross-match per annuncio → Area Radar → giro acquisizione → report Excel → email/WhatsApp → salvataggio storico.

Le notifiche operative riportano in testa: **DOVE ANDARE → COSA CERCO → PREZZO → AZIONE**.

Prima di qualsiasi attività commerciale resta valida la regola: **APRI FONTE E VERIFICA CONTATTO**.
