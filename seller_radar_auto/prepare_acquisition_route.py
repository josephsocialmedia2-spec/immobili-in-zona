#!/usr/bin/env python3
"""Prepara il Giro Acquisizione senza perdere il database master.

Principio:
- work_queue.csv / state.json = MASTER Seller Radar, tutti i territori catalogati;
- municipalities.csv enabled=1 = territorio operativo del Giro di oggi;
- giro_acquisizione.csv = master completo classificato;
- giro_acquisizione_oggi.csv = opportunità attive nel territorio operativo;
- giro_da_verificare.csv = record del territorio con indirizzo incompleto;
- giro_backlog.csv = opportunità attive fuori dal territorio operativo;
- giro_funzionari.csv = sole fermate pronte effettivamente assegnate.
"""
import csv
import json
import os
import re
import unicodedata
from pathlib import Path

from f1_remote_bridge import build_import_url

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE = DATA / "state.json"
QUEUE = DATA / "work_queue.csv"
MUNICIPALITIES = ROOT / "municipalities.csv"

OUT = DATA / "giro_acquisizione.csv"
OUT_TODAY = DATA / "giro_acquisizione_oggi.csv"
OUT_VERIFY = DATA / "giro_da_verificare.csv"
OUT_BACKLOG = DATA / "giro_backlog.csv"
OUT_TEAM = DATA / "giro_funzionari.csv"
OUT_TEAM_JSON = DATA / "giro_funzionari.json"
OUT_SUMMARY = DATA / "giro_riepilogo.json"

TEAM_SIZE = max(1, int(os.getenv("F1_OPERATOR_COUNT", "10")))
EXCLUDED_TOWNS = {"sant ambrogio di torino"}
OUT_MARKET_STATES = {"USCITO_MERCATO", "REMOVED", "EXPIRED", "OUT"}

ADDRESS_RE = re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s,]{2,80}?[,\s]+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|[A-Za-z])?\b",
    re.I,
)
STREET_RE = re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s]{2,80}?(?=,|\s+-\s+|$)",
    re.I,
)
PRICE_PATTERNS = [
    re.compile(r"(?:€|eur(?:o)?)\s*([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})", re.I),
    re.compile(r"([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})\s*(?:€|eur(?:o)?)", re.I),
]


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"items": {}}
    except Exception:
        return {"items": {}}


def clean(v):
    return re.sub(r"\s+", " ", str(v or "")).strip(" ,.;")


def norm(v):
    s = unicodedata.normalize("NFKD", str(v or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_active_towns():
    if not MUNICIPALITIES.exists():
        raise SystemExit("municipalities.csv assente: impossibile definire il territorio operativo")
    with MUNICIPALITIES.open(encoding="utf-8-sig", newline="") as f:
        towns = {
            norm(r.get("comune"))
            for r in csv.DictReader(f)
            if r.get("enabled") == "1" and norm(r.get("comune"))
        }
    if "susa" not in towns:
        raise SystemExit("Territorio operativo non valido: Susa deve essere enabled=1")
    return towns


def exact_address(x):
    area = x.get("area_radar") or {}
    refs = area.get("reference_addresses") or []
    for a in refs:
        a = clean(a)
        m = ADDRESS_RE.search(a)
        if m:
            return clean(m.group(0)).replace(" /", "/").replace("/ ", "/")
        m = STREET_RE.search(a)
        if m:
            return clean(m.group(0))
    title = clean(x.get("title"))
    m = ADDRESS_RE.search(title)
    if m:
        return clean(m.group(0)).replace(" /", "/").replace("/ ", "/")
    m = STREET_RE.search(title)
    if m:
        return clean(m.group(0))
    street = clean(area.get("street"))
    if street:
        return street
    return "INDIRIZZO DA VERIFICARE"


def price_from_text(text):
    text = clean(text)
    for pat in PRICE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        n = int(re.sub(r"\D", "", m.group(1)))
        if 5000 <= n <= 20000000:
            return str(n)
    return ""


def current_price(x, fallback=""):
    hist = x.get("price_history") or []
    if hist and hist[-1].get("price"):
        return str(hist[-1].get("price"))
    if str(fallback or "").strip():
        return str(fallback).strip()
    inferred = price_from_text(f"{x.get('title','')} {x.get('snippet','')}")
    return inferred or "PREZZO DA VERIFICARE"


def action_for(address, opportunity_type, goal, pdf_url=""):
    if opportunity_type in {"CANTIERE_NUOVA_COSTRUZIONE", "IMPRESA_EDILE_PROGETTO"}:
        if pdf_url:
            return "APRI PDF → VERIFICA PROGETTO/IMPRESA → POI CONTATTA"
        if "DA VERIFICARE" in address:
            return "APRI FONTE → IDENTIFICA IMPRESA/CANTIERE → CONTATTA"
        return "VERIFICA CANTIERE → CONTATTA IMPRESA/COSTRUTTORE"
    if opportunity_type == "ATTIVITA_CESSIONE":
        return "VERIFICA ATTIVITA → CONTATTA TITOLARE/REFERENTE"
    if opportunity_type in {"COMMERCIALE_IMMOBILE", "UFFICIO_DIREZIONALE", "INDUSTRIALE_LOGISTICA", "TERRENO_SVILUPPO"}:
        if "DA VERIFICARE" in address:
            return "APRI FONTE → VERIFICA UBICAZIONE → CONTATTA"
        return "VAI IN ZONA / CONTATTA PER " + (goal or "OPPORTUNITA COMMERCIALE")
    if "DA VERIFICARE" in address:
        return "APRI FONTE E VERIFICA INDIRIZZO"
    return "VAI IN ZONA"


def int_score(row):
    try:
        return int(row.get("SCORE") or 0)
    except (TypeError, ValueError):
        return 0


def write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


active_towns = load_active_towns()
state = load_state()
items = state.get("items") or {}
by_url = {(x.get("url") or "").strip(): x for x in items.values()}

rows = []
fields = []
if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []

extras = [
    "DOVE_ANDRE", "COSA_CERCO", "PREZZO_OPERATIVO", "ISTRUZIONE_OPERATIVA",
    "F1_INDIRIZZO_REMOTO_URL", "TERRITORIO_OPERATIVO", "STATO_GIRO"
]
fields += [k for k in extras if k not in fields]

route_rows = []
for r in rows:
    x = by_url.get((r.get("URL") or "").strip(), {})
    address = exact_address(x)
    thing = clean(x.get("title") or r.get("TITOLO"))[:180] or "OPPORTUNITA DA VERIFICARE"
    price = current_price(x, r.get("PREZZO"))
    otype = r.get("TIPO_OPPORTUNITA") or x.get("opportunity_type") or "RESIDENZIALE"
    stage = r.get("FASE_PROGETTO") or x.get("project_stage") or ""
    goal = r.get("OBIETTIVO_COMMERCIALE") or x.get("commercial_goal") or "ACQUISIZIONE IMMOBILE"
    target = r.get("TARGET") or x.get("lead_target") or "IMMOBILE"

    thing_norm = norm(thing)
    if "terreno edificabile" in thing_norm or "area edificabile" in thing_norm or "lotto edificabile" in thing_norm:
        otype = "TERRENO_SVILUPPO"
        target = "TERRENO"
        if not goal or goal == "ACQUISIZIONE IMMOBILE":
            goal = "ACQUISIZIONE TERRENO / SVILUPPO"

    pdf_url = r.get("PDF_DA_VERIFICARE") or ""
    action = action_for(address, otype, goal, pdf_url)
    comune = r.get("COMUNE", "")
    in_active_territory = norm(comune) in active_towns
    lifecycle = (r.get("STATO") or x.get("lifecycle") or "").strip().upper()
    market_active = lifecycle not in OUT_MARKET_STATES

    if not market_active:
        route_state = "STORICO_NON_ATTIVO"
    elif not in_active_territory:
        route_state = "BACKLOG"
    elif "DA VERIFICARE" in address:
        route_state = "DA_VERIFICARE"
    else:
        route_state = "FERMATA_PRONTA"

    r["DOVE_ANDRE"] = address
    r["COSA_CERCO"] = thing
    r["PREZZO_OPERATIVO"] = price
    r["ISTRUZIONE_OPERATIVA"] = action
    r["F1_INDIRIZZO_REMOTO_URL"] = build_import_url(r)
    r["TERRITORIO_OPERATIVO"] = "SI" if in_active_territory else "NO"
    r["STATO_GIRO"] = route_state

    route_rows.append({
        "FUNZIONARIO": "",
        "NUM_FUNZIONARIO": "",
        "STATO_ASSEGNAZIONE": "",
        "TERRITORIO_OPERATIVO": r["TERRITORIO_OPERATIVO"],
        "STATO_GIRO": route_state,
        "STATO_MERCATO": lifecycle,
        "PRIORITA": r.get("PRIORITA", ""),
        "SCORE": r.get("SCORE", ""),
        "TIPO_OPPORTUNITA": otype,
        "TARGET": target,
        "FASE_PROGETTO": stage,
        "OBIETTIVO_COMMERCIALE": goal,
        "COMUNE": comune,
        "DOVE_ANDRE": address,
        "COSA_CERCO": thing,
        "PREZZO": price,
        "FONTE": r.get("FONTE", ""),
        "SELLER_SIGNAL": r.get("INDIZIO_INSERZIONISTA", ""),
        "AZIONE": action,
        "PDF_DA_VERIFICARE": pdf_url,
        "URL": r.get("URL", ""),
        "F1_INDIRIZZO_REMOTO_URL": r["F1_INDIRIZZO_REMOTO_URL"],
    })

if rows:
    write_csv(QUEUE, fields, rows)

# Assegnazione team: esclusivamente fermate pronte nel territorio operativo.
ready_rows = [r for r in route_rows if r.get("STATO_GIRO") == "FERMATA_PRONTA"]
best_by_town = {}
for r in ready_rows:
    town_key = norm(r.get("COMUNE"))
    if not town_key or town_key in EXCLUDED_TOWNS:
        continue
    score = int_score(r)
    if town_key not in best_by_town or score > best_by_town[town_key]["score"]:
        best_by_town[town_key] = {"score": score, "comune": r.get("COMUNE", "")}

ranked_towns = sorted(best_by_town.items(), key=lambda kv: kv[1]["score"], reverse=True)[:TEAM_SIZE]
assignment = {
    town_key: {"funzionario": idx + 1, "comune": info["comune"], "score_comune": info["score"]}
    for idx, (town_key, info) in enumerate(ranked_towns)
}

for r in route_rows:
    if r.get("STATO_GIRO") == "FERMATA_PRONTA":
        a = assignment.get(norm(r.get("COMUNE")))
        if a:
            r["FUNZIONARIO"] = f"FUNZIONARIO {a['funzionario']}"
            r["NUM_FUNZIONARIO"] = str(a["funzionario"])
            r["STATO_ASSEGNAZIONE"] = "ASSEGNATO"
        else:
            r["STATO_ASSEGNAZIONE"] = "IN_ATTESA_TEAM"
    else:
        r["STATO_ASSEGNAZIONE"] = r.get("STATO_GIRO", "")

route_fields = [
    "FUNZIONARIO", "NUM_FUNZIONARIO", "STATO_ASSEGNAZIONE",
    "TERRITORIO_OPERATIVO", "STATO_GIRO", "STATO_MERCATO",
    "PRIORITA", "SCORE", "TIPO_OPPORTUNITA", "TARGET", "FASE_PROGETTO", "OBIETTIVO_COMMERCIALE",
    "COMUNE", "DOVE_ANDRE", "COSA_CERCO", "PREZZO",
    "FONTE", "SELLER_SIGNAL", "AZIONE", "PDF_DA_VERIFICARE", "URL", "F1_INDIRIZZO_REMOTO_URL"
]

route_rows.sort(key=lambda r: int_score(r), reverse=True)
today_rows = [r for r in route_rows if r.get("TERRITORIO_OPERATIVO") == "SI" and r.get("STATO_GIRO") != "STORICO_NON_ATTIVO"]
today_order = {"FERMATA_PRONTA": 0, "DA_VERIFICARE": 1}
today_rows.sort(key=lambda r: (today_order.get(r.get("STATO_GIRO"), 9), -int_score(r)))
verify_rows = [r for r in today_rows if r.get("STATO_GIRO") == "DA_VERIFICARE"]
backlog_rows = [r for r in route_rows if r.get("STATO_GIRO") == "BACKLOG"]
team_rows = [r for r in route_rows if r.get("STATO_ASSEGNAZIONE") == "ASSEGNATO"]
team_rows.sort(key=lambda r: (int(r.get("NUM_FUNZIONARIO") or 999), -int_score(r)))

write_csv(OUT, route_fields, route_rows)
write_csv(OUT_TODAY, route_fields, today_rows)
write_csv(OUT_VERIFY, route_fields, verify_rows)
write_csv(OUT_BACKLOG, route_fields, backlog_rows)
write_csv(OUT_TEAM, route_fields, team_rows)

team_summary = {
    "team_size_configured": TEAM_SIZE,
    "assigned_staff": len(assignment),
    "unassigned_staff": max(0, TEAM_SIZE - len(assignment)),
    "assignments": [
        {
            "funzionario": f"FUNZIONARIO {a['funzionario']}",
            "numero": a["funzionario"],
            "comune": a["comune"],
            "score_comune": a["score_comune"],
            "righe_lavoro": sum(1 for r in team_rows if int(r.get("NUM_FUNZIONARIO") or 0) == a["funzionario"]),
            "residenziale": sum(1 for r in team_rows if int(r.get("NUM_FUNZIONARIO") or 0) == a["funzionario"] and r.get("TIPO_OPPORTUNITA") == "RESIDENZIALE"),
            "commerciale": sum(1 for r in team_rows if int(r.get("NUM_FUNZIONARIO") or 0) == a["funzionario"] and r.get("TIPO_OPPORTUNITA") in {"COMMERCIALE_IMMOBILE", "UFFICIO_DIREZIONALE", "INDUSTRIALE_LOGISTICA", "ATTIVITA_CESSIONE", "TERRENO_SVILUPPO"}),
            "cantieri_imprese": sum(1 for r in team_rows if int(r.get("NUM_FUNZIONARIO") or 0) == a["funzionario"] and r.get("TIPO_OPPORTUNITA") in {"CANTIERE_NUOVA_COSTRUZIONE", "IMPRESA_EDILE_PROGETTO"}),
            "pdf_da_verificare": sum(1 for r in team_rows if int(r.get("NUM_FUNZIONARIO") or 0) == a["funzionario"] and r.get("PDF_DA_VERIFICARE")),
        }
        for a in sorted(assignment.values(), key=lambda x: x["funzionario"])
    ],
}
OUT_TEAM_JSON.write_text(json.dumps(team_summary, ensure_ascii=False, indent=2), encoding="utf-8")

summary = {
    "seller_master_totali": len(route_rows),
    "seller_attivi_master": sum(1 for r in route_rows if r.get("STATO_GIRO") != "STORICO_NON_ATTIVO"),
    "storico_non_attivo": sum(1 for r in route_rows if r.get("STATO_GIRO") == "STORICO_NON_ATTIVO"),
    "nel_territorio_attivo": len(today_rows),
    "fermate_pronte": len(ready_rows),
    "indirizzo_da_verificare": len(verify_rows),
    "backlog_fuori_territorio": len(backlog_rows),
    "fermate_assegnate_team": len(team_rows),
    "territori_master": len({norm(r.get("COMUNE")) for r in route_rows if norm(r.get("COMUNE"))}),
    "territori_operativi_configurati": len(active_towns),
    "centro_operativo": "Susa",
    "raggio_operativo": "20 km",
}
OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

print(
    "GIRO ACQUISIZIONE: "
    f"master={summary['seller_master_totali']}; attivi={summary['seller_attivi_master']}; "
    f"territorio={summary['nel_territorio_attivo']}; fermate_pronte={summary['fermate_pronte']}; "
    f"da_verificare={summary['indirizzo_da_verificare']}; backlog={summary['backlog_fuori_territorio']}; "
    f"assegnate={summary['fermate_assegnate_team']}."
)
