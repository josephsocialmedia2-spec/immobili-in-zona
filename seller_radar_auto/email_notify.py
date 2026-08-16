#!/usr/bin/env python3
import csv, json, os, smtplib
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
QUEUE = DATA / "work_queue.csv"
SENT = DATA / "email_sent.json"

SMTP_HOST = os.getenv("F1_EMAIL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("F1_EMAIL_SMTP_PORT", "465"))
EMAIL_USER = os.getenv("F1_EMAIL_USER", "").strip()
EMAIL_PASS = os.getenv("F1_EMAIL_APP_PASSWORD", "").strip()
EMAIL_TO = "agenzia.realmediapro@gmail.com"

if not (EMAIL_USER and EMAIL_PASS):
    print("Email non configurata: mancano F1_EMAIL_USER / F1_EMAIL_APP_PASSWORD")
    raise SystemExit(0)

sent = set()
if SENT.exists():
    try:
        sent = set(json.loads(SENT.read_text(encoding="utf-8")).get("sent_ids", []))
    except Exception:
        sent = set()

rows = []
if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

# Identifica in modo stabile l'annuncio tramite URL.
def row_id(r):
    return (r.get("URL") or "").strip()

new_rows = [r for r in rows if r.get("STATO") == "NEW" and row_id(r) and row_id(r) not in sent]

if not new_rows:
    print("Nessuna nuova pubblicazione da inviare via email.")
    raise SystemExit(0)

lines = ["F1 IMMOBILIARE — NUOVE PUBBLICAZIONI RADAR", ""]
for r in new_rows:
    prezzo = r.get("PREZZO") or "—"
    if prezzo != "—":
        try:
            prezzo = f"€ {int(float(prezzo)):,}".replace(",", ".")
        except Exception:
            pass
    lines.extend([
        f"COMUNE: {r.get('COMUNE','')}",
        f"FONTE: {r.get('FONTE','')}",
        f"TITOLO: {r.get('TITOLO','')}",
        f"PREZZO: {prezzo}",
        f"SCORE: {r.get('SCORE','')}/100",
        f"PRIORITÀ: {r.get('PRIORITA','')}",
        f"INDIZIO: {r.get('INDIZIO_INSERZIONISTA','')}",
        f"MOTIVI: {r.get('MOTIVI','')}",
        f"LINK: {r.get('URL','')}",
        "",
        "------------------------------",
        "",
    ])

msg = EmailMessage()
msg["From"] = EMAIL_USER
msg["To"] = EMAIL_TO
msg["Subject"] = f"F1 Radar — {len(new_rows)} nuova/e pubblicazione/i"
msg.set_content("\n".join(lines))

with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
    smtp.login(EMAIL_USER, EMAIL_PASS)
    smtp.send_message(msg)

for r in new_rows:
    sent.add(row_id(r))
SENT.write_text(json.dumps({"sent_ids": sorted(sent)}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Email inviata a {EMAIL_TO}: {len(new_rows)} nuova/e pubblicazione/i.")
