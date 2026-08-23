# Manuale tecnico

## Architettura

- Flask locale su `127.0.0.1:8765`;
- SQLite in `%LOCALAPPDATA%\F1IndirizzoRemoto\data`;
- documenti in `uploads`, lettere in `letters`, esportazioni in `exports`;
- query parametrizzate e CSRF per tutte le azioni di modifica;
- adapter radar con whitelist dei campi.

## Aggiornamento

Eseguire nuovamente `INSTALLA.bat`. Il codice viene aggiornato; database, documenti ed esportazioni restano nella cartella dati esterna all'applicazione.

## Self-test

`python -m f1_indirizzo_remoto.app --self-test`

## Backup

Il database puo essere copiato a programma chiuso. Prima di migrazioni future usare `Database.backup()`. Un database non integro non viene sovrascritto: viene copiato nei backup e l'avvio si interrompe.
