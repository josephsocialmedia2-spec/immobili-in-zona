# ACQUISIZIONE SUSA CRM

CRM locale-first per F1 Immobiliare, dedicato all'acquisizione nel Comune di Susa. Mantiene schede, immobili, richiami, note cronologiche, prequalifica venditore, importazioni e una base di conoscenza consultabile con Ollama.

## Funzioni già operative

- Dashboard con scaduti, attività di oggi, prossimi 7 giorni e informazioni mancanti.
- Ricerca globale per nome, telefono, email, indirizzo, fonte e contenuto delle note.
- Schede contatto/immobile con stato, priorità, prossima azione e data di richiamo.
- Nota obbligatoria dopo ogni contatto e storico append-only.
- Le 12 domande operative F1 e classificazione automatica A/B/C.
- Importazione multipla di JPG/PNG, CSV/TSV, XLSX, TXT/MD, PDF, DOCX, JSON/HTML.
- OCR locale tramite Tesseract; lettura PDF tramite `pdftotext`; analisi opzionale con Ollama.
- Anteprima e correzione prima della conferma; controllo duplicati per telefono, email e indirizzo.
- Archivio RAG locale delle chat e dei testi importati, con fonti nelle risposte.
- Modello Ollama configurabile e rilevamento automatico dei modelli installati.
- Backup scaricabile JSON, CSV ed Excel con data/ora nel nome.
- Sincronizzazione Supabase manuale dei soli dati strutturati confermati.
- Promemoria del lunedì con apertura di [Contenuti F1](https://lunedi-contenuti-f1.josephsocialmedia.chatgpt.site/).
- Installazione Windows con collegamento Desktop `ACQUISIZIONE SUSA CRM`.

## Avvio rapido sul PC

Requisiti: Node.js 22.5 o successivo. Ollama è necessario solo per le funzioni IA.

```bash
cp .env.example .env
node src/server.mjs
```

Aprire `http://127.0.0.1:4173`. Il progetto non richiede pacchetti NPM esterni.

Per proteggere l'accesso locale, modificare `.env`:

```env
CRM_PIN=un-pin-lungo-e-riservato
```

## Installazione Windows

1. Scaricare il repository come ZIP e decomprimerlo.
2. Installare [Node.js LTS](https://nodejs.org/) e [Ollama](https://ollama.com/).
3. Fare clic destro su `scripts/install-windows.ps1` e scegliere **Esegui con PowerShell**.
4. Usare il collegamento `ACQUISIZIONE SUSA CRM` creato sul Desktop.

Per OCR di fotografie installare Tesseract con lingua italiana. Per PDF testuali installare Poppler (`pdftotext`). Se non sono disponibili, il file viene comunque conservato localmente e l'interfaccia mostra un avviso.

## Ollama

Avviare Ollama e installare almeno un modello, per esempio:

```bash
ollama pull llama3.2
```

Per immagini e screenshot scegliere un modello visivo installato. Il CRM rileva i modelli da `http://127.0.0.1:11434/api/tags`; la scelta viene salvata nelle impostazioni locali.

Le chat importate non “addestrano” il modello: vengono suddivise in sezioni e recuperate con una ricerca RAG locale. I file personali non sono inviati a servizi IA esterni.

## Supabase online

1. Creare un progetto Supabase dedicato.
2. Eseguire `supabase/migrations/001_initial_schema.sql` nel SQL Editor.
3. Attivare l'accesso email/password in Supabase Auth.
4. Copiare `.env.example` in `.env` e compilare `SUPABASE_URL`, la chiave necessaria e `SUPABASE_USER_ID` con l'UUID dell'utente proprietario.
5. Riavviare il CRM e usare **Sincronizza dati confermati**.

Lo schema abilita Row Level Security. La chiave `service_role`, se usata dal companion locale, deve restare esclusivamente nel file `.env` del PC e non deve mai essere inserita in GitHub o nel browser.

## Importazione del CRM Excel esistente

Aprire **Importa dati**, selezionare il file XLSX e controllare l'anteprima. Il lettore XLSX usa Python 3 e soltanto la libreria standard. In alternativa esportare il foglio in CSV. Nessuna riga viene salvata finché non si preme **Conferma nel CRM**.

## Test

```bash
npm test
npm run check
```

GitHub Actions esegue gli stessi controlli a ogni push e pull request.

## Privacy

Questo repository deve contenere esclusivamente codice, documentazione, migrazioni e test. Non aggiungere database, backup, foto, fogli Excel, nomi reali, telefoni, email o note cliente. Vedi [SECURITY.md](SECURITY.md).
