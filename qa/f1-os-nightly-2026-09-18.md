# F1 OS Nightly QA — 2026-09-18

Commit verificato: `bfa0c65fe0111d8ec02ed1fb8a11b8e15ffaf855`

| Componente | Test | Esito | Errore / evidenza | Correzione applicata | Retest |
|---|---|---|---|---|---|
| Repository GitHub | HEAD + tree ricorsivo | PASS | repository accessibile | nessuna | PASS |
| OGGI COSA FACCIO | ricerca `oggi.html` + fetch Contents API | FAIL | `oggi.html` assente dal repository HEAD | nessuna: sorgente canonica non disponibile | FAIL |
| PWA | ricerca manifest/service worker | FAIL | manifest PWA e service worker non individuati nel tree HEAD | nessuna: non ricostruito da zero | FAIL |
| Build / Actions | ultime run accessibili | PASS PARZIALE | nessuna failure nel campione recente; combined status HEAD pending con 0 status | nessuna | PASS PARZIALE |
| GitHub Pages / link | verifica asset pubblicabili | BLOCCATO | Pages E2E non certificabile; `oggi.html` assente dal branch sorgente | nessuna | BLOCCATO |
| Radar | pipeline + dati correnti | PASS PARZIALE | workflow presenti; snapshot storico disponibile fino al 2026-09-17 | nessuna | PASS PARZIALE |
| CRM | sorgenti/test | PASS STRUTTURALE | server, DB, Supabase adapter e test presenti; runtime non eseguito | nessuna | BLOCCATO E2E |
| Database/cloud | integrazione repository | BLOCCATO | adapter Supabase presente; sessione cloud autenticata non disponibile in questa run | nessuna | BLOCCATO |
| Funnel Engine | ricerca componente canonico | FAIL / NON IDENTIFICATO | nessun modulo canonico Funnel Engine identificato | nessuna | FAIL |
| Role Play | ricerca componente canonico | FAIL / NON IDENTIFICATO | nessun modulo Role Play identificato nel tree HEAD | nessuna | FAIL |
| App smartphone | asset PWA/mobile | FAIL / BLOCCATO E2E | PWA canonica assente; dispositivo reale non disponibile | nessuna | FAIL |
| Backup | backup/restore canonico | BLOCCATO | nessun backup cloud certificabile con gli strumenti disponibili; restore non eseguito | nessuna | BLOCCATO |
| Centrale Telefonate | sorgenti | PASS STRUTTURALE / BLOCCATO E2E | `windows_valle_susa/f1_mobile_server.py`, centrale e smoke test presenti; localhost/PC Windows non accessibile | nessuna | BLOCCATO E2E |
| Integrazioni | registry | PASS STRUTTURALE | `seller_radar_auto/integrations.json` presente | nessuna | PASS STRUTTURALE |

## Esito

NON CERTIFICATO. Errori aperti: entrypoint `oggi.html` assente; PWA canonica assente; Funnel Engine e Role Play non identificati nel tree corrente. Componenti dipendenti da cloud autenticato, PC Windows, localhost o smartphone reale restano BLOCCATI.

Non sono state applicate correzioni funzionali: ripristinare o ricostruire i componenti mancanti senza una sorgente canonica verificabile sarebbe una modifica non sicura.