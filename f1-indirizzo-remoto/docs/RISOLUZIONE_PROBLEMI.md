# Risoluzione problemi

## L'icona non apre nulla

Esegui di nuovo `INSTALLA.bat`. L'installer ripristina i componenti e rilancia il self-test senza cancellare il database.

## La porta e gia utilizzata

Se F1 Indirizzo Remoto e gia aperto, il doppio clic apre la finestra esistente. Se un altro programma usa la porta 8765, chiudilo o configura una porta diversa tramite `F1_IR_PORT`.

## PDF senza testo

Il documento e probabilmente scansionato. Installa Tesseract OCR con lingua italiana; in alternativa inserisci manualmente i dati e confermali dalla fonte.

## CAPTCHA o accesso richiesto

Interrompi l'automazione. Accedi manualmente e carica il documento solo dopo averlo scaricato legittimamente.

## Database non integro

L'applicazione crea una copia protetta del file danneggiato e tenta il ripristino dall'ultimo backup SQLite valido. Se nessun backup e utilizzabile, si interrompe senza cancellare il file danneggiato.
