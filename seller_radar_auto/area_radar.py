#!/usr/bin/env python3
"""F1 Seller Radar — radar di via / zona.

Per ogni annuncio, anche di agenzia:
- ricava la via/civico dalle evidenze pubbliche già raccolte;
- cerca altri indirizzi pubblicamente indicizzati sulla stessa via;
- produce azioni VAI_IN_ZONA;
- produce CHIAMA solo per numeri già presenti tra i contatti pubblici dell'annuncio
  e presenti nell'eventuale lista rpo_approved.csv.

Non associa numeri a residenti/vicini per cognome o sola prossimità geografica.
"""
import csv, html, json, re
from pathlib import Path
from search_engine import search as web_search

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE = DATA / "state.json"
QUEUE = DATA / "work_queue.csv"
OUT = DATA / "area_radar.csv"
RPO = ROOT / "rpo_approved.csv"

ADDRESS_RE = re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s]{2,80}?\s+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|\s*[A-Za-z])?\b",
    re.I,
)

def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def norm_phone(v):
    d = re.sub(r"\D", "", v or "")
    return d[2:] if d.startswith("39") and len(d) > 10 else d

def search(q, count=12):
    results, _error = web_search(q, count)
    return results

def address_list(text):
    vals, seen = [], set()
    for m in ADDRESS_RE.finditer(clean(text)):
        v = re.sub(r"\s+", " ", m.group(0)).strip(" ,.;")
        k = v.casefold()
        if k not in seen:
            seen.add(k); vals.append(v)
    return vals

def street_of(address):
    if not address:
        return ""
    s = re.sub(r"\s+", " ", clean(address)).strip(" ,.;")
    s = re.sub(r"\s+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|\s*[A-Za-z])?\s*$", "", s).strip()
    return s

def load_rpo():
    approved = set()
    if not RPO.exists():
        return approved
    with RPO.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("approved") or "").strip().upper() != "SI":
                continue
            p = norm_phone(r.get("telefono") or "")
            if p:
                approved.add(p)
    return approved

try:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"items": {}}
except Exception:
    state = {"items": {}}
items = state.get("items") or {}
rpo_ok = load_rpo()
rows = []

for item_id, x in items.items():
    e = x.get("enrichment") or {}
    comune = (x.get("comune") or "").strip()
    hints = list(e.get("address_hints") or [])

    if not hints:
        q = f'"{(x.get("title") or "")[:120]}" "{comune}"'
        for r in search(q, 8):
            hints += address_list(f"{r['title']} {r.get('snippet','')}")
    hints = list(dict.fromkeys(hints))[:5]

    area = {
        "reference_addresses": hints,
        "street": "",
        "nearby_public_addresses": [],
        "actions": [],
    }

    if hints:
        street = street_of(hints[0])
        area["street"] = street
        found = []
        if street:
            q = f'"{street}" "{comune}"'
            for r in search(q, 20):
                for a in address_list(f"{r['title']} {r.get('snippet','')}"):
                    if street.casefold() in a.casefold() and a.casefold() not in {z.casefold() for z in found}:
                        found.append(a)
        all_addresses = list(dict.fromkeys(hints + found))[:20]
        area["nearby_public_addresses"] = all_addresses
        for a in all_addresses:
            area["actions"].append({"azione": "VAI_IN_ZONA", "target": a, "telefono": "", "stato": "PRONTO"})
            rows.append({
                "ITEM_ID": item_id,
                "COMUNE": comune,
                "TIPO_ANNUNCIO": x.get("seller_hint", "NON_DETERMINATO"),
                "VIA_RADAR": street,
                "AZIONE": "VAI_IN_ZONA",
                "TARGET": a,
                "TELEFONO": "",
                "STATO": "PRONTO",
                "FONTE": x.get("url", ""),
            })

    for c in e.get("public_contacts") or []:
        if c.get("type") != "PHONE" or c.get("confidence") not in {"HIGH", "MEDIUM"}:
            continue
        p = norm_phone(c.get("value") or "")
        approved = p in rpo_ok
        azione = "CHIAMA" if approved else "VERIFICA_RPO"
        stato = "PRONTO" if approved else "BLOCCATO_FINCHÉ_NON_VERIFICATO"
        area["actions"].append({"azione": azione, "target": e.get("seller_name") or "inserzionista", "telefono": c.get("value", ""), "stato": stato})
        rows.append({
            "ITEM_ID": item_id,
            "COMUNE": comune,
            "TIPO_ANNUNCIO": x.get("seller_hint", "NON_DETERMINATO"),
            "VIA_RADAR": area.get("street", ""),
            "AZIONE": azione,
            "TARGET": e.get("seller_name") or "inserzionista",
            "TELEFONO": c.get("value", ""),
            "STATO": stato,
            "FONTE": c.get("source_url", ""),
        })

    x["area_radar"] = area

state["items"] = items
STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

fields = ["ITEM_ID","COMUNE","TIPO_ANNUNCIO","VIA_RADAR","AZIONE","TARGET","TELEFONO","STATO","FONTE"]
with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig", newline="") as f:
        qrows = list(csv.DictReader(f))
        qfields = list(qrows[0].keys()) if qrows else []
    extra = ["VIA_RADAR","INDIRIZZI_ZONA","AZIONE_ZONA"]
    qfields += [k for k in extra if k not in qfields]
    by_url = {(x.get("url") or "").strip(): x for x in items.values()}
    for r in qrows:
        item = by_url.get((r.get("URL") or "").strip(), {})
        area = item.get("area_radar") or {}
        r["VIA_RADAR"] = area.get("street", "")
        r["INDIRIZZI_ZONA"] = " | ".join((area.get("nearby_public_addresses") or [])[:8])
        acts = area.get("actions") or []
        labels = []
        if any(a.get("azione") == "VAI_IN_ZONA" for a in acts): labels.append("VAI IN ZONA")
        if any(a.get("azione") == "CHIAMA" for a in acts): labels.append("CHIAMA")
        if any(a.get("azione") == "VERIFICA_RPO" for a in acts): labels.append("VERIFICA RPO")
        r["AZIONE_ZONA"] = " + ".join(labels)
    with QUEUE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=qfields); w.writeheader(); w.writerows(qrows)

print(f"Area Radar: {len(rows)} azioni generate su {len(items)} annunci.")
