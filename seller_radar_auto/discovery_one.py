#!/usr/bin/env python3
"""Discovery isolata: un Comune/zona per job GitHub Actions.

Radar multi-canale F1 / Real Media Pro:
- residenziale;
- immobili commerciali, uffici, capannoni e attività;
- terreni/sviluppo;
- imprese edili, nuovi cantieri e progetti in corso o programmati;
- atti pubblici/PDF urbanistici da verificare manualmente.

Usa esclusivamente risultati pubblici del web. L'indirizzo non è requisito
d'ingresso: viene arricchito nei passaggi successivi. I PDF vengono solo
segnalati come fonte pubblica da verificare: il Radar non li usa per creare
automaticamente liste commerciali di persone fisiche.
"""
import csv, html, json, os, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from search_engine import search

ROOT = Path(__file__).resolve().parent
PORTALS = ROOT / "portal_catalog.csv"
OUT = Path(os.getenv("F1_DISCOVERY_OUT", str(ROOT / "data" / "discovery_one.json")))
COMUNE = os.getenv("F1_COMUNE", "").strip()
TRACK = {"gclid", "fbclid", "msclkid", "ref", "source"}
BROAD_PATHS = {"", "^/.*$"}

PROPERTY_WORDS = (
    "casa", "appartamento", "villa", "villetta", "trilocale", "bilocale",
    "quadrilocale", "immobile", "terratetto", "monolocale", "rustico",
    "casale", "cascina", "mansarda", "attico", "alloggio", "baita"
)
COMMERCIAL_PROPERTY_WORDS = (
    "negozio", "locale commerciale", "ufficio", "studio", "capannone",
    "magazzino", "laboratorio", "showroom", "deposito", "immobile commerciale",
    "immobile industriale", "direzionale", "logistica", "autorimessa"
)
BUSINESS_WORDS = (
    "attività", "attivita", "azienda", "bar", "ristorante", "pizzeria",
    "negozio", "parrucchiere", "estetica", "tabaccheria", "edicola",
    "albergo", "hotel", "b&b", "bed and breakfast", "officina", "carrozzeria",
    "palestra", "studio professionale"
)
SALE_WORDS = (
    "vendita", "vendesi", "vende", "in vendita", "for sale", "asta",
    "giudiziaria", "aggiudicato", "venduto", "prezzo ribassato", "ribasso",
    "prezzo ridotto", "non disponibile", "€", "euro", "eur"
)
COMMERCIAL_TRANSACTION_WORDS = SALE_WORDS + (
    "affitto", "affittasi", "locazione", "in locazione", "cessione",
    "cedesi", "subentro", "mura", "licenza"
)
BUSINESS_TRANSFER_WORDS = (
    "cessione attività", "cessione attivita", "cedesi attività", "cedesi attivita",
    "attività in vendita", "attivita in vendita", "azienda in vendita", "subentro",
    "cessione azienda", "cessione ramo", "vendesi attività", "vendesi attivita"
)
CONSTRUCTION_WORDS = (
    "impresa edile", "impresa costruzioni", "costruzioni", "costruttore",
    "general contractor", "developer immobiliare", "sviluppatore immobiliare",
    "edilizia", "società di costruzioni", "societa di costruzioni"
)
PROJECT_WORDS = (
    "cantiere", "nuova costruzione", "nuove costruzioni", "in costruzione",
    "lavori in corso", "prossima realizzazione", "nuovo complesso",
    "nuova residenza", "residenza", "complesso residenziale", "lotto",
    "lottizzazione", "permesso di costruire", "scia", "pec", "piano esecutivo",
    "piano particolareggiato", "variante urbanistica", "progetto approvato"
)
DEVELOPMENT_WORDS = (
    "terreno edificabile", "area edificabile", "lotto edificabile", "terreno industriale",
    "area industriale", "area commerciale", "sviluppo immobiliare", "lottizzazione"
)
PUBLIC_DOCUMENT_WORDS = (
    "albo pretorio", "amministrazione trasparente", "delibera", "deliberazione",
    "determina", "determinazione", "permesso di costruire", "scia", "pec",
    "piano regolatore", "piano esecutivo", "piano particolareggiato",
    "variante urbanistica", "urbanistica", "edilizia privata", "lottizzazione",
    "progetto approvato", "convenzione urbanistica"
)
STREET_RE = re.compile(r"\b(via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo|localit[aà])\b", re.I)


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def fold(s):
    return clean(s).casefold()


def norm(url):
    p = urlparse(url or "")
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not (k.lower().startswith("utm_") or k.lower() in TRACK)]
    return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(q), ""))


def is_pdf_url(url):
    p = urlparse(url or "")
    return p.path.casefold().endswith(".pdf") or ".pdf" in p.path.casefold()


def host_matches(host, expected):
    host = (host or "").lower().split(":")[0]
    expected = (expected or "").lower().strip()
    if not expected:
        return True
    if expected.startswith("*."):
        return host.endswith(expected[1:])
    base = expected.removeprefix("www.")
    return host == expected or host == base or host.endswith("." + base)


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def portal_for_url(url, portals):
    h = urlparse(url).netloc
    for p in portals:
        d = (p.get("domain") or "").strip()
        if d and host_matches(h, d):
            return p
    return None


def location_terms(comune):
    c = fold(comune)
    if c == "ferriera di buttigliera alta":
        return ("ferriera", "buttigliera alta")
    return (c,)


def location_matches(text, url, comune):
    t = fold(text)
    u = (url or "").casefold().replace("-", " ")
    return any(term and (term in t or term in u) for term in location_terms(comune))


def contains_any(text, words):
    return any(w in text for w in words)


def relevant(url, text, comune, mode="residential", portal=None):
    t = fold(text)
    p = urlparse(url)
    if portal:
        domain = (portal.get("domain") or "").strip()
        if domain and not host_matches(p.netloc, domain):
            return False
        path_regex = (portal.get("path_regex") or "").strip()
        if path_regex and path_regex not in BROAD_PATHS and not re.search(path_regex, p.path, re.I):
            return False
    if not location_matches(text, url, comune):
        return False

    if mode == "residential":
        return contains_any(t, PROPERTY_WORDS) and contains_any(t, SALE_WORDS)
    if mode == "commercial_property":
        return contains_any(t, COMMERCIAL_PROPERTY_WORDS) and contains_any(t, COMMERCIAL_TRANSACTION_WORDS)
    if mode == "business_sale":
        return contains_any(t, BUSINESS_WORDS) and contains_any(t, BUSINESS_TRANSFER_WORDS)
    if mode == "development":
        return contains_any(t, DEVELOPMENT_WORDS) and (
            contains_any(t, COMMERCIAL_TRANSACTION_WORDS) or contains_any(t, PROJECT_WORDS)
        )
    if mode == "construction":
        return contains_any(t, PROJECT_WORDS) and (
            contains_any(t, CONSTRUCTION_WORDS) or
            "cantiere" in t or "nuova costruzione" in t or "lavori in corso" in t or
            "permesso di costruire" in t or "lottizzazione" in t
        )
    if mode == "public_document":
        return is_pdf_url(url) and (
            contains_any(t, PUBLIC_DOCUMENT_WORDS) or
            contains_any(t, PROJECT_WORDS) or
            contains_any(t, CONSTRUCTION_WORDS) or
            contains_any(t, DEVELOPMENT_WORDS)
        )
    return False


def price(text):
    for pat in [
        r"(?:€|eur(?:o)?)\s*([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})",
        r"([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})\s*(?:€|eur(?:o)?)",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            n = int(re.sub(r"\D", "", m.group(1)))
            if 5000 <= n <= 20000000:
                return n
    return None


def seller_hint(text):
    t = fold(text)
    if re.search(r"\b(no agenzie|senza agenzia|da privato|annuncio privato|inserzionista privato|vendita privata|privato vende|vendo privatamente|solo privati|astenersi agenzie)\b", t, re.I):
        return "INDIZIO_PRIVATO"
    if re.search(r"\b(agenzia immobiliare|tecnocasa|tecnorete|tempocasa|gabetti|re/?max|franchising immobiliare|mediazione immobiliare)\b", t, re.I):
        return "INDIZIO_AGENZIA"
    return "NON_DETERMINATO"


def market_signal(text, label=""):
    t = fold(text + " " + label)
    out = []
    rules = [
        ("ASTA", r"\b(asta|giudiziaria|tribunale|aggiudicat)\b"),
        ("RIBASSO", r"\b(ribass|prezzo ridotto|prezzo trattabile|riduzione prezzo)\b"),
        ("STORICO_USCITA", r"\b(venduto|non disponibile|non più disponibile|annuncio rimosso|scaduto)\b"),
        ("PRIVATO", r"\b(privato|no agenzie|astenersi agenzie)\b"),
        ("AGENZIA", r"\b(agenzia immobiliare|tecnocasa|tecnorete|tempocasa|gabetti|re/?max)\b"),
        ("LOCAZIONE", r"\b(affitto|affittasi|locazione)\b"),
        ("CESSIONE_ATTIVITA", r"\b(cessione|cedesi|subentro)\b"),
        ("CANTIERE", r"\b(cantiere|in costruzione|lavori in corso|nuova costruzione)\b"),
        ("SVILUPPO", r"\b(lottizzazione|terreno edificabile|area edificabile|permesso di costruire)\b"),
        ("ATTO_PUBBLICO_PDF", r"\b(albo pretorio|delibera|determina|urbanistica|permesso di costruire|scia|piano esecutivo|variante urbanistica)\b"),
    ]
    for lab, pat in rules:
        if re.search(pat, t, re.I):
            out.append(lab)
    return ",".join(out) or "VENDITA"


def project_stage(text):
    t = fold(text)
    if re.search(r"\b(lavori in corso|cantiere aperto|in costruzione|in fase di costruzione)\b", t):
        return "IN_CORSO"
    if re.search(r"\b(permesso di costruire|progetto approvato|scia|pec|piano esecutivo|lottizzazione approvata)\b", t):
        return "AUTORIZZATO_PROGRAMMATO"
    if re.search(r"\b(prossima realizzazione|in progetto|prossimo cantiere|di prossima costruzione)\b", t):
        return "PROGRAMMATO"
    if re.search(r"\b(nuova costruzione|nuove costruzioni|nuovo complesso|nuova residenza)\b", t):
        return "NUOVA_COSTRUZIONE"
    return ""


def commercial_goal(opportunity_type):
    goals = {
        "RESIDENZIALE": "ACQUISIZIONE IMMOBILE",
        "COMMERCIALE_IMMOBILE": "ACQUISIZIONE / LOCAZIONE IMMOBILE COMMERCIALE",
        "ATTIVITA_CESSIONE": "INCARICO CESSIONE ATTIVITA / IMMOBILE",
        "UFFICIO_DIREZIONALE": "ACQUISIZIONE / LOCAZIONE UFFICIO",
        "INDUSTRIALE_LOGISTICA": "ACQUISIZIONE CAPANNONE / MAGAZZINO",
        "TERRENO_SVILUPPO": "SVILUPPO / ACQUISIZIONE AREA",
        "CANTIERE_NUOVA_COSTRUZIONE": "CONTATTA COSTRUTTORE: COMMERCIALIZZAZIONE + MARKETING",
        "IMPRESA_EDILE_PROGETTO": "CONTATTA IMPRESA: CANTIERE, SOCIAL, LEAD GEN, SITO, VENDITE",
    }
    return goals.get(opportunity_type, "VALUTA OPPORTUNITA")


if not COMUNE:
    raise SystemExit("F1_COMUNE mancante")
portals = [r for r in load_csv(PORTALS) if r.get("enabled") == "1"]

# Query ad ampia copertura. Il campo 'type' viene conservato fino alla coda operativa.
plans = [
    {"label":"Mercato residenziale", "query":f'"{COMUNE}" ("in vendita" OR vendesi OR vendita) (casa OR appartamento OR villa OR immobile)', "count":30, "private":False, "portal":None, "mode":"residential", "type":"RESIDENZIALE"},
    {"label":"Tipologie residenziali", "query":f'"{COMUNE}" (appartamento OR villa OR rustico OR casale OR cascina OR "casa indipendente" OR mansarda OR attico) ("in vendita" OR vendita OR vendesi)', "count":30, "private":False, "portal":None, "mode":"residential", "type":"RESIDENZIALE"},
    {"label":"Ribassi", "query":f'"{COMUNE}" (ribassato OR ribasso OR "prezzo ridotto" OR "prezzo trattabile") (casa OR appartamento OR villa OR rustico OR immobile)', "count":25, "private":False, "portal":None, "mode":"residential", "type":"RESIDENZIALE"},
    {"label":"Aste", "query":f'"{COMUNE}" ("asta giudiziaria" OR "vendita giudiziaria" OR "asta immobiliare" OR tribunale) (casa OR appartamento OR villa OR immobile)', "count":25, "private":False, "portal":None, "mode":"residential", "type":"RESIDENZIALE"},
    {"label":"Privati", "query":f'"{COMUNE}" ("privato vende" OR "no agenzie" OR "astenersi agenzie" OR "da privato") (casa OR appartamento OR villa OR rustico)', "count":25, "private":True, "portal":None, "mode":"residential", "type":"RESIDENZIALE"},
    {"label":"Storico uscite", "query":f'"{COMUNE}" (venduto OR "annuncio non disponibile" OR "immobile non disponibile" OR "annuncio rimosso") (casa OR appartamento OR villa OR immobile)', "count":20, "private":False, "portal":None, "mode":"residential", "type":"RESIDENZIALE"},

    {"label":"Commerciale negozi/locali", "query":f'"{COMUNE}" (negozio OR "locale commerciale" OR showroom) (vendita OR affitto OR locazione OR cedesi)', "count":25, "private":False, "portal":None, "mode":"commercial_property", "type":"COMMERCIALE_IMMOBILE"},
    {"label":"Uffici e direzionale", "query":f'"{COMUNE}" (ufficio OR studio OR direzionale) (vendita OR affitto OR locazione)', "count":25, "private":False, "portal":None, "mode":"commercial_property", "type":"UFFICIO_DIREZIONALE"},
    {"label":"Capannoni logistica", "query":f'"{COMUNE}" (capannone OR magazzino OR laboratorio OR deposito OR logistica) (vendita OR affitto OR locazione)', "count":25, "private":False, "portal":None, "mode":"commercial_property", "type":"INDUSTRIALE_LOGISTICA"},
    {"label":"Cessione attività", "query":f'"{COMUNE}" ("cessione attività" OR "cedesi attività" OR "attività in vendita" OR "azienda in vendita" OR subentro) (bar OR ristorante OR negozio OR azienda OR attività)', "count":25, "private":False, "portal":None, "mode":"business_sale", "type":"ATTIVITA_CESSIONE"},
    {"label":"Terreni e sviluppo", "query":f'"{COMUNE}" ("terreno edificabile" OR "area edificabile" OR "lotto edificabile" OR lottizzazione OR "area commerciale") (vendita OR progetto OR costruzione)', "count":25, "private":False, "portal":None, "mode":"development", "type":"TERRENO_SVILUPPO"},

    {"label":"Nuove costruzioni e cantieri", "query":f'"{COMUNE}" (cantiere OR "nuova costruzione" OR "nuove costruzioni" OR "in costruzione" OR "lavori in corso" OR "nuovo complesso" OR "nuova residenza")', "count":30, "private":False, "portal":None, "mode":"construction", "type":"CANTIERE_NUOVA_COSTRUZIONE"},
    {"label":"Imprese edili con progetti", "query":f'"{COMUNE}" ("impresa edile" OR "impresa costruzioni" OR costruttore OR "società di costruzioni") (cantiere OR progetto OR "nuova costruzione" OR "lavori in corso" OR residenza)', "count":30, "private":False, "portal":None, "mode":"construction", "type":"IMPRESA_EDILE_PROGETTO"},
    {"label":"Progetti autorizzati", "query":f'"{COMUNE}" ("permesso di costruire" OR SCIA OR PEC OR "piano esecutivo" OR lottizzazione OR "progetto approvato") (residenziale OR commerciale OR costruzione OR edilizia)', "count":25, "private":False, "portal":None, "mode":"construction", "type":"IMPRESA_EDILE_PROGETTO"},

    {"label":"PDF urbanistica e permessi", "query":f'"{COMUNE}" filetype:pdf ("permesso di costruire" OR SCIA OR "piano esecutivo" OR lottizzazione OR "variante urbanistica")', "count":20, "private":False, "portal":None, "mode":"public_document", "type":"IMPRESA_EDILE_PROGETTO"},
    {"label":"PDF cantieri e progetti", "query":f'"{COMUNE}" filetype:pdf (cantiere OR "nuova costruzione" OR "progetto approvato" OR edilizia OR urbanistica)', "count":20, "private":False, "portal":None, "mode":"public_document", "type":"IMPRESA_EDILE_PROGETTO"},
    {"label":"PDF Albo Pretorio edilizia", "query":f'"{COMUNE}" filetype:pdf ("albo pretorio" OR "amministrazione trasparente" OR delibera OR determina) (edilizia OR urbanistica OR lottizzazione OR costruire)', "count":20, "private":False, "portal":None, "mode":"public_document", "type":"IMPRESA_EDILE_PROGETTO"},
]

for p in portals:
    template = (p.get("query_template") or "").strip()
    if not template:
        continue
    try:
        count = max(1, min(30, int(p.get("max_results") or 10)))
    except Exception:
        count = 10
    plans.append({
        "label": (p.get("label") or "Fonte configurata").strip(),
        "query": template.replace("{comune}", COMUNE),
        "count": count,
        "private": p.get("private_intent") == "1",
        "portal": p,
        "mode": "residential",
        "type": "RESIDENZIALE",
    })

accepted = []
statuses = []
seen = set()
for plan in plans:
    results, error = search(plan["query"], plan["count"])
    nacc = 0
    for r in results:
        url = norm(r.get("url", ""))
        title = clean(r.get("title", ""))
        snippet = clean(r.get("snippet", ""))
        evidence = f"{title} {snippet}".strip()
        detected = portal_for_url(url, portals)
        expected = plan.get("portal")
        portal = expected or detected
        if not relevant(url, evidence, COMUNE, plan.get("mode", "residential"), portal) or url in seen:
            continue
        seen.add(url)
        nacc += 1
        source = (detected or expected or {}).get("label") or plan["label"]
        private_intent = bool(plan["private"] or ((detected or expected) and (detected or expected).get("private_intent") == "1"))
        otype = plan.get("type", "RESIDENZIALE")
        accepted.append({
            "comune": COMUNE,
            "fonte": source.strip(),
            "url": url,
            "title": title[:220],
            "snippet": snippet[:700],
            "private_intent": private_intent,
            "domain_rule": ((detected or expected) or {}).get("domain", "") or "",
            "path_rule": ((detected or expected) or {}).get("path_regex", "") or "",
            "seller_hint": seller_hint(evidence),
            "price": price(evidence),
            "has_street_hint": bool(STREET_RE.search(evidence)),
            "market_signal": market_signal(evidence, plan["label"]),
            "query_label": plan["label"],
            "opportunity_type": otype,
            "lead_target": "IMPRESA/AZIENDA" if otype in {"ATTIVITA_CESSIONE", "CANTIERE_NUOVA_COSTRUZIONE", "IMPRESA_EDILE_PROGETTO"} else "IMMOBILE",
            "project_stage": project_stage(evidence),
            "commercial_goal": commercial_goal(otype),
            "public_pdf": is_pdf_url(url),
            "discovery_engine": "PUBLIC_DORK_MATRIX_V5",
        })
    statuses.append({
        "FONTE": plan["label"], "COMUNE": COMUNE,
        "STATO": "OK" if not error else "ERROR", "ULTIMO_CONTROLLO": now(),
        "RISULTATI_GREZZI": len(results), "ACCETTATI": nacc,
        "MESSAGGIO": error, "QUERY": plan["query"],
    })

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({"comune": COMUNE, "results": accepted, "status": statuses}, ensure_ascii=False, indent=2), encoding="utf-8")
print(
    f"DISCOVERY {COMUNE}: {len(accepted)} accettati su {len(plans)} query; " +
    ", ".join(f"{s['FONTE']}={s['STATO']}:{s['ACCETTATI']}/{s['RISULTATI_GREZZI']}" for s in statuses)
)