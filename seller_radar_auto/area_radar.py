#!/usr/bin/env python3
"""F1 Seller Radar — radar di via / zona.

Principio operativo a due binari:
- LEAD_DIRETTO: annuncio con indizio privato. Puo generare VAI_IN_ZONA e,
  solo se il contatto e gia pubblico nell'annuncio e approvato RPO, CHIAMA.
- AREA_OPPORTUNITY: annuncio con indizio agenzia. Non viene scartato: se
  l'indirizzo e utile genera VAI_IN_ZONA per presidio territoriale, ma non
  usa il telefono dell'agenzia come contatto del proprietario.
- AREA_DA_VERIFICARE: inserzionista non determinato. Si usa per il giro in
  zona finche la natura dell'annuncio non e verificata.

Per ogni annuncio, anche di agenzia:
- ricava la via/civico dalle evidenze pubbliche gia raccolte;
- cerca altri indirizzi pubblicamente indicizzati sulla STESSA via;
- produce azioni VAI_IN_ZONA;
- produce CHIAMA solo per LEAD_DIRETTO, per numeri gia presenti tra i
  contatti pubblici dell'annuncio e presenti in rpo_approved.csv.

Non associa numeri a residenti/vicini per cognome o sola prossimita geografica.
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

def same_street(address, street):
    return bool(address and street and street_of(address).casefold() == street.casefold())

def opportunity_type(seller_hint):
    hint = (seller_hint or "NON_DETERMINATO").strip().upper()
    if hint == "INDIZIO_PRIVATO":
        return "LEAD_DIRETTO"
    if hint == "INDIZIO_AGENZIA":
        return "AREA_OPPORTUNITY"
    return "AREA_DA_VERIFICARE"

def opportunity_reason(kind):
    if kind == "LEAD_DIRETTO":
        return "PRIVATO: possibile contatto diretto dopo verifica fonte/RPO"
    if kind == "AREA_OPPORTUNITY":
        return "AGENZIA: immobile attivo usato come segnale territoriale; presidia via/stabile"
    return "INSERZIONISTA DA VERIFICARE: usa indirizzo come segnale territoriale"

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
    kind = opportunity_type(x.get("seller_hint"))
    reason = opportunity_reason(kind)
    hints = list(e.get("address_hints") or [])

    if not hints:
        q = f'"{(x.get("title") or "")[:120]}" "{comune}"'
        for r in search(q, 8):
            hints += address_list(f"{r['title']} {r.get('snippet','')}")
    hints = list(dict.fromkeys(hints))[:8]

    area = {
        "opportunity_type": kind,
        "opportunity_reason": reason,
        "reference_addresses": hints,
        "street": "",
        "nearby_public_addresses": [],
        "actions": [],
    }

    if hints:
        street = street_of(hints[0])
        area["street"] = street
        # Un radar = una via. Scarta eventuali altri indirizzi presenti in pagine aggregate.
        same_hints = [a for a in hints if same_street(a, street)]
        found = []
        if street:
            q = f'"{street}" "{comune}"'
            for r in search(q, 20):
                for a in address_list(f"{r['title']} {r.get('snippet','')}"):
                    if same_street(a, street) and a.casefold() not in {z.casefold() for z in found}:
                        found.append(a)
        all_addresses = list(dict.fromkeys(same_hints + found))[:20]
        area["nearby_public_addresses"] = all_addresses
        for a in all_addresses:
            area["actions"].append({
                "azione": "VAI_IN_ZONA",
                "target": a,
                "telefono": "",
                "stato": "PRONTO",
                "tipo_opportunita": kind,
            })
            rows.append({
                "ITEM_ID": item_id,
                "COMUNE": comune,
                "TIPO_ANNUNCIO": x.get("seller_hint", "NON_DETERMINATO"),
                "TIPO_OPPORTUNITA": kind,
                "MOTIVO": reason,
                "VIA_RADAR": street,
                "AZIONE": "VAI_IN_ZONA",
                "TARGET": a,
                "TELEFONO": "",
                "STATO": "PRONTO",
                "FONTE": x.get("url", ""),
            })

    # I contatti pubblici possono diventare azione CHIAMA solo per LEAD_DIRETTO.
    # Per AREA_OPPORTUNITY non si usa il recapito dell'agenzia come recapito del proprietario.
    if kind == "LEAD_DIRETTO":
        for c in e.get("public_contacts") or []:
            if c.get("type") != "PHONE" or c.get("confidence") not in {"HIGH", "MEDIUM"}:
                continue
            p = norm_phone(c.get("value") or "")
            approved = p in rpo_ok
            azione = "CHIAMA" if approved else "VERIFICA_RPO"
            stato = "PRONTO" if approved else "BLOCCATO_FINCHE_NON_VERIFICATO"
            area["actions"].append({
                "azione": azione,
                "target": e.get("seller_name") or "inserzionista",
                "telefono": c.get("value", ""),
                "stato": stato,
                "tipo_opportunita": kind,
            })
            rows.append({
                "ITEM_ID": item_id,
                "COMUNE": comune,
                "TIPO_ANNUNCIO": x.get("seller_hint", "NON_DETERMINATO"),
                "TIPO_OPPORTUNITA": kind,
                "MOTIVO": reason,
                "VIA_RADAR": area.get("street", ""),
                "AZIONE": azione,
                "TARGET": e.get("seller_name") or "inserzionista",
                "TELEFONO": c.get("value", ""),
                "STATO": stato,
                "FONTE": c.get("source_url", ""),
            })

    x["area_radar"] = area
    x["opportunity_type"] = kind

state["items"] = items
STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

fields = [
    "ITEM_ID","COMUNE","TIPO_ANNUNCIO","TIPO_OPPORTUNITA","MOTIVO",
    "VIA_RADAR","AZIONE","TARGET","TELEFONO","STATO","FONTE"
]
with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig", newline="") as f:
        qrows = list(csv.DictReader(f))
        qfields = list(qrows[0].keys()) if qrows else []
    extra = ["TIPO_OPPORTUNITA","MOTIVO_AREA","VIA_RADAR","INDIRIZZI_ZONA","AZIONE_ZONA"]
    qfields += [k for k in extra if k not in qfields]
    by_url = {(x.get("url") or "").strip(): x for x in items.values()}
    for r in qrows:
        item = by_url.get((r.get("URL") or "").strip(), {})
        area = item.get("area_radar") or {}
        r["TIPO_OPPORTUNITA"] = area.get("opportunity_type", opportunity_type(item.get("seller_hint")))
        r["MOTIVO_AREA"] = area.get("opportunity_reason", opportunity_reason(r["TIPO_OPPORTUNITA"]))
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

lead_direct = sum(1 for x in items.values() if opportunity_type(x.get("seller_hint")) == "LEAD_DIRETTO")
area_opp = sum(1 for x in items.values() if opportunity_type(x.get("seller_hint")) == "AREA_OPPORTUNITY")
print(
    f"Area Radar: {len(rows)} azioni generate su {len(items)} annunci. "
    f"LEAD_DIRETTO={lead_direct}; AREA_OPPORTUNITY={area_opp}."
)
