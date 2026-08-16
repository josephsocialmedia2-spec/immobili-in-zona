#!/usr/bin/env python3
import csv, json, os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "state.json"
SENT = ROOT / "data" / "whatsapp_sent.json"
ROUTES = ROOT / "whatsapp_routes.csv"

TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
API_VERSION = os.getenv("WHATSAPP_API_VERSION", "").strip()
DRY_RUN = os.getenv("WHATSAPP_DRY_RUN", "0").strip() == "1"


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_routes():
    routes = {}
    with ROUTES.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("enabled") != "1":
                continue
            comune = (row.get("comune") or "").strip()
            secret = (row.get("recipient_secret") or "").strip()
            routes[comune] = {
                "gruppo": (row.get("gruppo") or "").strip(),
                "recipient_secret": secret,
            }
    return routes


def euro(v):
    if not v:
        return "prezzo non rilevato"
    try:
        return f"€{int(v):,}".replace(",", ".")
    except Exception:
        return str(v)


def build_message(group, rows):
    lines = [f"F1 IMMOBILIARE — NUOVE PUBBLICAZIONI | {group}", ""]
    for r in rows:
        x = r["item"]
        hist = x.get("price_history") or []
        price = hist[-1].get("price") if hist else None
        hint = x.get("seller_hint", "NON_DETERMINATO")
        seller = "PRIVATO / NO AGENZIE" if hint == "INDIZIO_PRIVATO" else "NUOVO"
        lines.extend([
            f"{x.get('comune','')} — {seller}",
            f"{x.get('title','').strip()}",
            f"Prezzo: {euro(price)} | Score: {x.get('score','—')}/100 | Fonte: {x.get('fonte','')}",
            x.get("url", ""),
            "",
        ])
    lines.append("APRI FONTE E VERIFICA CONTATTO.")
    return "\n".join(lines).strip()


def send_text(to, body):
    if DRY_RUN:
        print(f"DRY RUN -> {to}\n{body}\n")
        return True, "dry-run"
    if not TOKEN or not PHONE_ID or not API_VERSION:
        return False, "mancano WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_API_VERSION"
    endpoint = f"https://graph.facebook.com/{API_VERSION}/{PHONE_ID}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": True, "body": body},
    }).encode("utf-8")
    req = Request(endpoint, data=payload, method="POST", headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    })
    try:
        with urlopen(req, timeout=25) as resp:
            return 200 <= resp.status < 300, resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        return False, e.read().decode("utf-8", errors="replace") or str(e)
    except (URLError, TimeoutError, OSError) as e:
        return False, str(e)


state = load_json(STATE, {"items": {}})
sent_state = load_json(SENT, {"sent_new_ids": [], "log": []})
sent_ids = set(sent_state.get("sent_new_ids", []))
routes = load_routes()

pending_by_recipient = {}
for item_id, x in (state.get("items") or {}).items():
    if x.get("lifecycle") != "NEW" or item_id in sent_ids:
        continue
    route = routes.get(x.get("comune", ""))
    if not route:
        print(f"NESSUNA ROTTA: {x.get('comune')} {item_id}")
        continue
    recipient = os.getenv(route["recipient_secret"], "").strip()
    if not recipient:
        print(f"DESTINATARIO NON CONFIGURATO: {route['recipient_secret']} per {x.get('comune')}")
        continue
    key = (recipient, route["gruppo"])
    pending_by_recipient.setdefault(key, []).append({"id": item_id, "item": x})

for (recipient, group), rows in pending_by_recipient.items():
    body = build_message(group, rows)
    ok, result = send_text(recipient, body)
    print(("INVIATO" if ok else "ERRORE") + f" -> {group} / {recipient}: {result}")
    if ok:
        for row in rows:
            sent_ids.add(row["id"])
            sent_state.setdefault("log", []).append({
                "id": row["id"],
                "comune": row["item"].get("comune", ""),
                "gruppo": group,
                "recipient_secret": routes[row["item"].get("comune", "")]["recipient_secret"],
            })

sent_state["sent_new_ids"] = sorted(sent_ids)
sent_state["log"] = sent_state.get("log", [])[-1000:]
SENT.write_text(json.dumps(sent_state, ensure_ascii=False, indent=2), encoding="utf-8")
