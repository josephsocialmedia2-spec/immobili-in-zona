#!/usr/bin/env python3
"""Prepara il giro operativo F1: dove andare, cosa cercare e prezzo."""
import csv, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE = DATA / "state.json"
QUEUE = DATA / "work_queue.csv"
OUT = DATA / "giro_acquisizione.csv"

ADDRESS_RE = re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s,]{2,80}?[,\s]+\d{1,4}(?:/[A-Za-z0-9]+|[A-Za-z])?\b",
    re.I,
)


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"items": {}}
    except Exception:
        return {"items": {}}


def clean(v):
    return re.sub(r"\s+", " ", str(v or "")).strip(" ,.;")


def exact_address(x):
    area = x.get("area_radar") or {}
    refs = area.get("reference_addresses") or []
    for a in refs:
        a = clean(a)
        if ADDRESS_RE.search(a):
            return a
    title = clean(x.get("title"))
    m = ADDRESS_RE.search(title)
    if m:
        return clean(m.group(0))
    street = clean(area.get("street"))
    if street:
        return f"{street} — CIVICO DA VERIFICARE"
    return "INDIRIZZO DA VERIFICARE"


def current_price(x, fallback=""):
    hist = x.get("price_history") or []
    if hist and hist[-1].get("price"):
        return str(hist[-1].get("price"))
    return str(fallback or "")


def action_for(address):
    if "DA VERIFICARE" in address:
        return "APRI FONTE E VERIFICA INDIRIZZO"
    return "VAI IN ZONA"


state = load_state()
items = state.get("items") or {}
by_url = {(x.get("url") or "").strip(): x for x in items.values()}

rows = []
fields = []
if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []

extras = ["DOVE_ANDRE", "COSA_CERCO", "PREZZO_OPERATIVO", "ISTRUZIONE_OPERATIVA"]
fields += [k for k in extras if k not in fields]

route_rows = []
for r in rows:
    x = by_url.get((r.get("URL") or "").strip(), {})
    address = exact_address(x)
    thing = clean(x.get("title") or r.get("TITOLO"))[:180] or "IMMOBILE DA VERIFICARE"
    price = current_price(x, r.get("PREZZO"))
    action = action_for(address)

    r["DOVE_ANDRE"] = address
    r["COSA_CERCO"] = thing
    r["PREZZO_OPERATIVO"] = price
    r["ISTRUZIONE_OPERATIVA"] = action

    route_rows.append({
        "PRIORITA": r.get("PRIORITA", ""),
        "SCORE": r.get("SCORE", ""),
        "COMUNE": r.get("COMUNE", ""),
        "DOVE_ANDRE": address,
        "COSA_CERCO": thing,
        "PREZZO": price,
        "FONTE": r.get("FONTE", ""),
        "SELLER_SIGNAL": r.get("INDIZIO_INSERZIONISTA", ""),
        "AZIONE": action,
        "URL": r.get("URL", ""),
    })

if rows:
    with QUEUE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

route_fields = ["PRIORITA", "SCORE", "COMUNE", "DOVE_ANDRE", "COSA_CERCO", "PREZZO", "FONTE", "SELLER_SIGNAL", "AZIONE", "URL"]
route_rows.sort(key=lambda r: int(r.get("SCORE") or 0), reverse=True)
with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=route_fields)
    w.writeheader()
    w.writerows(route_rows)

print(f"GIRO ACQUISIZIONE: {len(route_rows)} righe preparate in {OUT.name}.")
