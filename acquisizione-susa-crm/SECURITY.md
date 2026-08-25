# Sicurezza e dati personali

- Il server locale ascolta su `127.0.0.1`: non è esposto automaticamente alla rete.
- Impostare `CRM_PIN` nel file `.env` per richiedere un PIN all'apertura.
- I file originali, il database SQLite e i backup restano in `data/` o `backups/`, cartelle escluse da Git.
- Non inserire chiavi, password o dati cliente nei file versionati.
- Ollama usa soltanto `http://127.0.0.1:11434`; nessun file viene inviato automaticamente a servizi IA esterni.
- Supabase riceve solo i record strutturati confermati quando l'operatore avvia la sincronizzazione.
- Le note e le prequalifiche sono append-only nello schema Supabase.

In caso di pubblicazione del server oltre il PC locale, usare HTTPS, autenticazione Supabase e un reverse proxy configurato da un tecnico.
