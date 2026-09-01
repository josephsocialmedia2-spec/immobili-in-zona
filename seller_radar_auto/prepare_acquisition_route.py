#!/usr/bin/env python3
"""Prepara il giro operativo F1: residenziale, commerciale, attività e cantieri."""
import csv, json, os, re, unicodedata
from pathlib import Path

from f1_remote_bridge import build_import_url

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE = DATA / "state.json"
QUEUE = DATA / "work_queue.csv"
OUT = DATA / "giro_acquisizione.csv"
OUT_TEAM = DATA / "giro_funzionari.csv"
OUT_TEAM_JSON = DATA / "giro_funzionari.json"

TEAM_SIZE = max(1, int(os.getenv("F1_OPERATOR_COUNT", "10")))
EXCLUDED_TOWNS = {"sant ambrogio di torino"}

ADDRESS_RE = re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s,]{2,80}?[,\s]+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|[A-Za-z])?\b",
    re.I,
)
# Una via/località senza numero civico è comunque una destinazione operativa utile.
# Questo evita che opportunità valide (es. terreni edificabili) restino nascoste
# in "INDIRIZZO DA VERIFICARE" quando il titolo contiene già la strada.
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


state = load_state()
items = state.get("items") or {}
by_url = {(x.get("url") or "").strip(): x for x in items.values()}

rows = []
fields = []
if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []

extras = ["DOVE_ANDRE", "COSA_CERCO", "PREZZO_OPERATIVO", "ISTRUZIONE_OPERATIVA", "F1_INDIRIZZO_REMOTO_URL"]
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

    # Normalizzazione trasversale: se Brief/Market Intelligence riconoscono un
    # terreno edificabile, anche il giro operativo deve trattarlo come sviluppo.
    thing_norm = norm(thing)
    if "terreno edificabile" in thing_norm or "area edificabile" in thing_norm or "lotto edificabile" in thing_norm:
        otype = "TERRENO_SVILUPPO"
        target = "TERRENO"
        if not goal or goal == "ACQUISIZIONE IMMOBILE":
            goal = "ACQUISIZIONE TERRENO / SVILUPPO"

    pdf_url = r.get("PDF_DA_VERIFICARE") or ""
    action = action_for(address, otype, goal, pdf_url)

    r["DOVE_ANDRE"] = address
    r["COSA_CERCO"] = thing
    r["PREZZO_OPERATIVO"] = price
    r["ISTRUZIONE_OPERATIVA"] = action
    r["F1_INDIRIZZO_REMOTO_URL"] = build_import_url(r)

    route_rows.append({
        "PRIORITA": r.get("PRIORITA", ""),
        "SCORE": r.get("SCORE", ""),
        "TIPO_OPPORTUNITA": otype,
        "TARGET": target,
        "FASE_PROGETTO": stage,
        "OBIETTIVO_COMMERCIALE": goal,
        "COMUNE": r.get("COMUNE", ""),
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
    with QUEUE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

route_rows.sort(key=lambda r: int(r.get("SCORE") or 0), reverse=True)

# Fino a 10 comuni/zone diversi, scelti dal miglior score. In ogni comune il
# funzionario riceve tutte le opportunità: residenziali, commerciali e cantieri.
best_by_town = {}
for r in route_rows:
    town_key = norm(r.get("COMUNE"))
    if not town_key or town_key in EXCLUDED_TOWNS:
        continue
    score = int(r.get("SCORE") or 0)
    if town_key not in best_by_town or score > best_by_town[town_key]["score"]:
        best_by_town[town_key] = {"score": score, "comune": r.get("COMUNE", "")}

ranked_towns = sorted(best_by_town.items(), key=lambda kv: kv[1]["score"], reverse=True)[:TEAM_SIZE]
assignment = {
    town_key: {"funzionario": idx + 1, "comune": info["comune"], "score_comune": info["score"]}
    for idx, (town_key, info) in enumerate(ranked_towns)
}

for r in route_rows:
    a = assignment.get(norm(r.get("COMUNE")))
    if a:
        r["FUNZIONARIO"] = f"FUNZIONARIO {a['funzionario']}"
        r["NUM_FUNZIONARIO"] = str(a["funzionario"])
        r["STATO_ASSEGNAZIONE"] = "ASSEGNATO"
    else:
        r["FUNZIONARIO"] = ""
        r["NUM_FUNZIONARIO"] = ""
        r["STATO_ASSEGNAZIONE"] = "BACKLOG"

route_fields = [
    "FUNZIONARIO", "NUM_FUNZIONARIO", "STATO_ASSEGNAZIONE",
    "PRIORITA", "SCORE", "TIPO_OPPORTUNITA", "TARGET", "FASE_PROGETTO", "OBIETTIVO_COMMERCIALE",
    "COMUNE", "DOVE_ANDRE", "COSA_CERCO", "PREZZO",
    "FONTE", "SELLER_SIGNAL", "AZIONE", "PDF_DA_VERIFICARE", "URL", "F1_INDIRIZZO_REMOTO_URL"
]
with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=route_fields); w.writeheader(); w.writerows(route_rows)

team_rows = [r for r in route_rows if r.get("STATO_ASSEGNAZIONE") == "ASSEGNATO"]
team_rows.sort(key=lambda r: (int(r.get("NUM_FUNZIONARIO") or 999), -int(r.get("SCORE") or 0)))
with OUT_TEAM.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=route_fields); w.writeheader(); w.writerows(team_rows)

summary = {
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
OUT_TEAM_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

print(
    f"GIRO ACQUISIZIONE: {len(route_rows)} opportunità; team {TEAM_SIZE}; "
    f"funzionari assegnati {len(assignment)}; output {OUT_TEAM.name}."
)
