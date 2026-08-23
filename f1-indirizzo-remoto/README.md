# F1 Indirizzo Remoto

Applicazione Windows locale per trasformare un indirizzo noto in una pratica F1 ordinata, verificabile e lavorabile.

Formula operativa:

`INDIRIZZO -> VERIFICA -> IMMOBILE -> TITOLARITA -> CONTATTO LECITO -> AZIONE -> CRM`

Il modulo e separato da `radar_dork.py`: riceve un indirizzo gia noto, apre fonti pubbliche, guida la verifica catastale e ipotecaria, legge localmente documenti caricati dall'operatore, controlla la tracciabilita dei contatti, genera lettere e aggiorna un CRM locale.

## Uso rapido su Windows

1. Apri `installer`.
2. Fai doppio clic su `INSTALLA.bat`.
3. Attendi `INSTALLAZIONE COMPLETATA`.
4. Sul Desktop fai doppio clic su **F1 INDIRIZZO REMOTO**.
5. Segui: **CLICCA -> INSERISCI -> VERIFICA -> SALVA -> CONTATTA/SPEDISCI**.

La prima installazione richiede Internet per scaricare i componenti Python. Dopo l'installazione, archivio, documenti, lettere ed esportazioni CSV/Excel/PDF/JSON funzionano localmente; soltanto l'apertura delle fonti web richiede una connessione.

L'applicazione ascolta soltanto su `127.0.0.1`. Il database, i documenti e le esportazioni rimangono nel profilo Windows dell'utente e non vengono caricati su GitHub.

Nel Seller Radar, gli annunci il cui indirizzo e civico sono sostenuti dal titolo della fonte mostrano **APRI IN F1 INDIRIZZO REMOTO**. Il pulsante precompila la nuova pratica ma non la salva automaticamente.

## Avvio per sviluppo

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt -r requirements-dev.txt
set PYTHONPATH=src
.venv/Scripts/python -m f1_indirizzo_remoto.app --open-browser
```

Su Linux/macOS sostituire i percorsi della virtualenv con `.venv/bin/...`.

## Self-test

```bash
python -m f1_indirizzo_remoto.app --self-test
```

## Sicurezza e privacy

- nessuna automazione di SPID, CIE, OTP, CAPTCHA o pagamenti;
- nessuna raccolta massiva di numeri domestici;
- nessun contatto azionabile senza fonte, data, soggetto, motivo, conferma e condizione d'uso;
- `NON CONTATTARE` prevale su ogni altra azione;
- documenti e dati reali sono esclusi dal repository.

Consulta `SECURITY.md`, `PRIVACY.md` e `docs/MANUALE_UTENTE.md`.
