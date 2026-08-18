# F1 IMMOBILIARE — SELLER SIGNAL → VOLANTINO A6

## Scopo
Ogni Seller Signal utile deve essere trasformato in un volantino territoriale di acquisizione rivolto ai proprietari della stessa via e della microzona. Il volantino NON pubblicizza l'immobile che ha generato il segnale e NON deve renderlo identificabile.

## Esecuzione giornaliera
- Orario operativo: ogni mattina alle **04:00 Europe/Rome**.
- GitHub è il punto di coordinamento del flusso.
- Il sistema legge i Seller Signal disponibili, prepara una direttiva per ogni segnale utile e la deposita nella coda GitHub.
- La coda resta in attesa della preparazione grafica.
- Le grafiche approvate vengono caricate su GitHub nella cartella `seller_radar_auto/flyer_pipeline/ready/YYYY-MM-DD/`.
- Al mattino Joseph deve poter scaricare i file pronti tramite Download.

## Input Seller Signal
Il Seller Signal può contenere: Comune, Via, tipologia immobile, prezzo attuale, prezzo precedente, percentuale di ribasso, privato/agenzia, tempo sul mercato, ribassi multipli, invenduto, score operativo, fonte e altri segnali commerciali.

## Regola privacy/comunicazione
NON inserire nel volantino:
- numero civico dell'immobile segnalato;
- prezzo preciso dell'immobile segnalato;
- nome del proprietario o inserzionista;
- link dell'annuncio;
- fotografie dell'immobile segnalato;
- dati che consentano di identificare direttamente l'immobile.

È consentito usare:
- Comune;
- Via, senza civico;
- zona limitrofa;
- tipo di Seller Signal;
- percentuale di ribasso quando presente;
- problema commerciale evidenziato dal segnale.

Esempio corretto: `Abbiamo rilevato nella zona un recente segnale di ribasso del 13,6%.`
Esempio vietato: `La casa di Via Maisonetta 114 è scesa da 110.000 € a 95.000 €.`

## Formato grafico obbligatorio
- **A6 verticale**.
- Dimensione fisica: **105 × 148 mm**.
- **Sfondo bianco**.
- Stile pulito, premium, locale e immediatamente leggibile.
- Output preferiti: **PDF pronto stampa + PNG/JPG anteprima**.
- Non usare fondi scuri o pieni colore.
- Non sovraccaricare la parte alta.

## Gerarchia del volantino
Il volantino è diviso in due zone.

### PARTE ALTA — GRANDE — 55/65% DELLA PAGINA
Questa parte deve essere leggibile in 3–5 secondi.

Titolo MOLTO GRANDE:
`🏠 VUOI VENDERE CASA IN QUESTA ZONA?`

Problema GRANDE, adattato al Seller Signal.

Se RIBASSO:
`📉 Un prezzo iniziale non corretto può portare a ribassi, tempi di vendita più lunghi e perdita di forza nella trattativa.`

Poi:
`Abbiamo rilevato nella zona un recente segnale di ribasso del [X]%.`

Se INVENDUTO / LUNGA PERMANENZA:
`⏳ Restare troppo tempo sul mercato può ridurre l'interesse degli acquirenti e indebolire la percezione del valore dell'immobile.`

Poi:
`Abbiamo rilevato nella zona un recente segnale di lunga permanenza sul mercato.`

Se RIBASSI MULTIPLI:
`📉 Correggere più volte il prezzo durante la vendita può indebolire il posizionamento dell'immobile.`

Poi:
`Abbiamo rilevato nella zona segnali di successive riduzioni di prezzo.`

Se FORTE CONCORRENZA:
`🏘️ Quando molti immobili simili competono nella stessa zona, prezzo, presentazione e strategia diventano determinanti.`

Poi:
`Abbiamo rilevato una presenza significativa di immobili concorrenti nella zona.`

Frase di passaggio:
`Prima di pubblicare il tuo immobile, scopri quale potrebbe essere il suo corretto posizionamento sul mercato.`

CTA MOLTO GRANDE:
`RICHIEDI UNA VALUTAZIONE GRATUITA`

### PARTE BASSA — PICCOLA — 35/45% DELLA PAGINA
Titolo:
`Con una prima analisi verifichiamo:`

Elenco sintetico:
- il possibile valore di mercato;
- gli immobili concorrenti attualmente in vendita;
- il corretto posizionamento del prezzo;
- eventuali criticità che potrebbero rallentare la vendita;
- la strategia per aumentare l'interesse sull'immobile.

Obiettivo:
`🎯 L'obiettivo: partire con una strategia corretta, ridurre il rischio di successivi ribassi e creare le condizioni per vendere più efficacemente.`

Brand:
`F1 IMMOBILIARE`
`Strategia • Valutazione • Promozione Immobiliare`

Localizzazione:
`📍 [COMUNE] – [VIA SENZA CIVICO] e zona limitrofa`

CTA finale:
`📲 Richiedi gratuitamente la tua prima analisi immobiliare.`

## Riferimenti F1 Immobiliare — obbligatori
Usare questi riferimenti e non inventarne altri:

- **Joseph Malafronte — Telefono e WhatsApp: +39 371 370 8294**
- **Aurigemma Francesca — Telefono e WhatsApp: +39 371 424 6300**
- **Email: f1immobiliaresusa@outlook.it**
- **Sito: https://f1immobiliare.com/**

Nel volantino A6 dare priorità visiva al contatto di **Joseph +39 371 370 8294**; inserire anche Francesca quando lo spazio resta leggibile.

## Immagini obbligatorie
- Usare logo, fotografie del team e immagini istituzionali F1 già approvate.
- Priorità agli asset presenti in `seller_radar_auto/flyer_pipeline/assets/`.
- Se si usano materiali dal sito F1, devono provenire esclusivamente da `f1immobiliare.com` e rappresentare F1 Immobiliare / il team reale.
- NON generare loghi alternativi.
- NON inventare persone, agenti o sedi.
- NON usare la foto dell'immobile che ha prodotto il Seller Signal.

## Regole di copy
NON promettere risultati garantiti.
Vietato: `Il tuo immobile sarà venduto più velocemente`, `Vendiamo sicuramente la tua casa`, `Ti garantiamo il prezzo migliore`.
Preferire: `creare le condizioni per vendere più efficacemente`, `ridurre il rischio di errori nel posizionamento`, `analizzare prezzo, concorrenza e strategia prima della pubblicazione`.

## Output per ogni Seller Signal
Generare sempre:
1. `seller_signal` — dati originari utili alla lavorazione;
2. `problema_commerciale` — ribasso / invenduto / ribassi multipli / concorrenza / altro;
3. `territorio` — Comune + Via senza civico;
4. `testo_grande` — titolo + problema + dato più forte + CTA;
5. `testo_piccolo` — analisi + obiettivo + brand + contatti;
6. `specifiche_grafiche` — A6 verticale, sfondo bianco, gerarchia 60/40;
7. `asset_da_usare` — immagini ufficiali F1;
8. `nome_file` — `F1_SellerSignal_[Comune]_[Via]_[TipoSegnale]_[YYYY-MM-DD]`.

## Flusso GitHub
1. **04:00 Europe/Rome** → leggere i Seller Signal.
2. Selezionare quelli utili.
3. Rimuovere civico e dati identificativi dal testo pubblico.
4. Preparare le direttive in `seller_radar_auto/flyer_pipeline/queue/YYYY-MM-DD/`.
5. Attendere la preparazione della grafica.
6. Caricare le grafiche finite in `seller_radar_auto/flyer_pipeline/ready/YYYY-MM-DD/`.
7. Pubblicare/aggiornare l'indice Download.
8. Joseph scarica al mattino i file pronti.

## Comando operativo finale
Ogni mattina alle 04:00 Europe/Rome, prendi i Seller Signal disponibili e trasformali in direttive per volantini F1 Immobiliare A6 verticali con sfondo bianco. Il Seller Signal è solo l'innesco commerciale territoriale: il destinatario è il proprietario che abita nella stessa via o microzona e potrebbe valutare di vendere. La prima parte del volantino deve essere grande e ad alto impatto; la seconda più piccola e informativa. Inserisci sempre i riferimenti ufficiali F1 e usa esclusivamente immagini F1 approvate. Deposita le direttive su GitHub, attendi che le grafiche vengano preparate e caricate nella cartella `ready`, quindi rendile disponibili per il Download mattutino.