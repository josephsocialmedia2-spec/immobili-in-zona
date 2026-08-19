# F1 Seller Radar AUTO

Radar automatico di opportunità immobiliari pubbliche per F1 Immobiliare. Il sistema esegue discovery, scoring, cross-match, Area Radar, prepara il giro di acquisizione e può inviare le nuove opportunità via email/WhatsApp quando le relative credenziali sono configurate.

## STANDARD OPERATIVO OUTPUT RADAR

Da questo momento ogni risultato operativo destinato al giro di acquisizione deve indicare sempre, nell'ordine:

1. COMUNE
2. VIA
3. NUMERO CIVICO
4. COSA CERCARE SUL POSTO
5. PREZZO ATTUALE
6. SEGNALE COMMERCIALE, quando disponibile: PRIVATO / NUOVO / RIBASSO / INVENDUTO / TRATTABILE / DA RISTRUTTURARE
7. FONTE E LINK DELL'ANNUNCIO, quando disponibili

Formato minimo obbligatorio:

COMUNE: [comune]
INDIRIZZO: [via] [numero civico]
COSA CERCARE: [tipo immobile / cartello / stabile / riferimento utile]
PREZZO: [euro]
SEGNALE: [se disponibile]
FONTE: [portale/link]

Regole:
- Non inventare mai il numero civico. Se non è pubblicato, scrivere: CIVICO DA VERIFICARE.
- Non inventare mai il prezzo. Se non è disponibile, scrivere: PREZZO DA VERIFICARE.
- Dare priorità ai risultati con indirizzo completo e verificabile.
- L'output deve essere immediatamente utilizzabile sul territorio: deve rispondere alla domanda **DOVE VADO, COSA CERCO, QUANTO COSTA**.
- Ordinare i risultati per priorità commerciale e, quando possibile, per percorso geografico efficiente.

## OUTPUT GENERATI

- `data/work_queue.csv` — coda completa del radar, arricchita con `DOVE_ANDRE`, `COSA_CERCO`, `PREZZO_OPERATIVO`, `ISTRUZIONE_OPERATIVA`.
- `data/giro_acquisizione.csv` — lista operativa ordinata per score.
- `data/area_radar.csv` — indirizzi pubblicamente rilevati e azioni territoriali.
- `data/state.json` — storico degli annunci monitorati.
- `dashboard.html` — dashboard pubblica.

## AUTOMAZIONE

GitHub Actions esegue il radar alle **08:30** e **18:30** ora italiana e può essere avviato manualmente.

Flusso: discovery per comune → merge → scoring → cross-match per annuncio → Area Radar → giro acquisizione → email/WhatsApp → salvataggio storico.

Le notifiche operative riportano in testa: **DOVE ANDARE → COSA CERCO → PREZZO → AZIONE**.

Prima di qualsiasi attività commerciale resta valida la regola: **APRI FONTE E VERIFICA CONTATTO**.
