#!/usr/bin/env python3
"""
F1 Seller Radar — public enrichment / cross-match.

Scopo:
- arricchire gli annunci già rilevati dal radar;
- cercare copie dello stesso immobile su altri portali e sul web pubblico;
- estrarre recapiti pubblicati nell'annuncio o in copie chiaramente riconducibili allo stesso immobile;
- conservare fonte, URL e livello di confidenza;
- NON inferire parenti o associare recapiti per sola coincidenza di cognome.

Solo libreria standard: adatto a GitHub Actions.
"""
import csv
import hashlib
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE = DATA / "state.json"
QUEUE = DATA / "work_queue.csv"
OUT = DATA / "public_enrichment.csv"
PORTALS = ROOT / "portal_catalog.csv"

UA = "F1SellerRadar-Enrichment/1.0 (+public-source-crossmatch)"
TIMEOUT = 18
MAX_ITEMS = int(os.getenv("F1_ENRICH_MAX", "35"))
MAX_RESULTS = int(os.getenv("F1_ENRICH_RESULTS", "8"))
MIN_SCORE = int(os.getenv("F1_ENRICH_MIN_SCORE", "45"))
TRACK = {"gclid", "fbclid", "msclkid", "ref", "source"}

PHONE_RE = re.compile(
    r"(?<!\d)(?:\+39[\s.\-]?)?(?:0\d{1,3}[\s.\-]?\d{5,8}|3\d{2}[\s.\-]?\d{6,7})(?!\d)"
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
ADDRESS_RE = re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s]{2,80}?\s+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|\s*[A-Za-z])?\b",
    re.I,
)

PORTAL_HINTS = (
    "immobiliare.it", "idealista.it", "casa.it", "trovacasa.it", "wikicasa.it",
    "subito.it", "bakeca.it", "trovit.it", "nestoria.it", "gate-away.com",
    "venderecasa.com", "tuttocasa.it", "tecnocasa.it", "tecnorete.it",
    "tempocasa.it", "facebook.com"
)
DIRECTORY_HINTS = ("paginebianche.it",)


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(s):
    s = re.sub(r"<script\b[^>]*>.*?</script>", " ", s or "", flags=re.I | re.S)
    s = re.sub(r"<style\b[^>]*>.*?</style>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def fold(s):
    return clean(s).casefold()


def norm(url):
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not (k.lower().startswith("utm_") or k.lower() in TRACK)]
    return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(q), ""))


def source_host(url):
    return urlparse(url).netloc.lower().removeprefix("www.")


def fetch(url, accept="text/html,application/xhtml+xml,*/*"):
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": accept,
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.6",
    })
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read(1_200_000)
            charset = r.headers.get_content_charset() or "utf-8"
            body = raw.decode(charset, errors="replace")
            if re.search(r"captcha|verify you are human|access denied|robot check", body, re.I):
                return False, r.status, "", "verifica umana / anti-bot"
            return 200 <= r.status < 400, r.status, body, ""
    except HTTPError as e:
        return False, e.code, "", str(e)
    except (URLError, TimeoutError, OSError) as e:
        return False, 0, "", str(e)


def bing_rss(query, count=MAX_RESULTS):
    url = "https://www.bing.com/search?" + urlencode({
        "q": query, "format": "rss", "count": str(count)
    })
    ok, status, body, error = fetch(
        url, "application/rss+xml,application/xml,text/xml,*/*"
    )
    if not ok:
        return [], {"status": status, "error": error, "url": url}
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        return [], {"status": status, "error": f"RSS non valido: {e}", "url": url}
    rows = []
    for n in root.findall(".//item")[:count]:
        link = norm((n.findtext("link") or "").strip())
        if not link.startswith(("http://", "https://")):
            continue
        rows.append({
            "title": clean(n.findtext("title") or "")[:240],
            "url": link,
            "snippet": clean(n.findtext("description") or "")[:600],
        })
    return rows, {"status": status, "error": "", "url": url}


def token_set(text):
    stop = {
        "della","delle","degli","dello","alla","alle","con","per","vendita","casa",
        "appartamento","immobile","villa","vaie","torino","to","euro","privato"
    }
    toks = re.findall(r"[a-zà-ÿ0-9]{3,}", fold(text))
    return {t for t in toks if t not in stop}


def similarity(a, b):
    A, B = token_set(a), token_set(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def extract_addresses(text):
    out = []
    seen = set()
    for m in ADDRESS_RE.finditer(clean(text)):
        value = re.sub(r"\s+", " ", m.group(0)).strip(" ,.;")
        k = value.casefold()
        if k not in seen:
            seen.add(k)
            out.append(value[:140])
    return out[:5]


def normalize_phone(value):
    digits = re.sub(r"\D", "", value)
    if digits.startswith("39") and len(digits) >= 11:
        digits = "+" + digits
    return digits


def extract_contacts(text, source_url, source_type, confidence):
    plain = clean(text)
    contacts = []
    seen = set()
    for m in PHONE_RE.finditer(plain):
        value = normalize_phone(m.group(0))
        nd = len(re.sub(r"\D", "", value))
        if nd < 9 or nd > 13:
            continue
        key = ("PHONE", value)
        if key not in seen:
            seen.add(key)
            contacts.append({
                "type": "PHONE",
                "value": value,
                "source_url": source_url,
                "source_type": source_type,
                "confidence": confidence,
            })
    for m in EMAIL_RE.finditer(plain):
        value = m.group(0).lower()
        if value.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            continue
        key = ("EMAIL", value)
        if key not in seen:
            seen.add(key)
            contacts.append({
                "type": "EMAIL",
                "value": value,
                "source_url": source_url,
                "source_type": source_type,
                "confidence": confidence,
            })
    return contacts[:12]


def extract_seller_name(raw):
    patterns = [
        r'"seller"\s*:\s*\{[^{}]{0,500}?"name"\s*:\s*"([^"]{3,100})"',
        r'"agent"\s*:\s*\{[^{}]{0,500}?"name"\s*:\s*"([^"]{3,100})"',
        r'(?:inserzionista|venditore|proprietario)\s*[:\-]\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ\'’\-]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ\'’\-]+){1,3})',
    ]
    for pat in patterns:
        m = re.search(pat, raw or "", re.I | re.S)
        if m:
            value = clean(m.group(1))
            if 3 <= len(value) <= 100:
                return value
    return ""


def portal_like(url):
    h = source_host(url)
    return any(h == d or h.endswith("." + d) for d in PORTAL_HINTS)


def directory_like(url):
    h = source_host(url)
    return any(h == d or h.endswith("." + d) for d in DIRECTORY_HINTS)


def same_property_score(item, result, address_hints):
    score = 0
    source_text = f"{item.get('title','')} {item.get('snippet','')}"
    target_text = f"{result.get('title','')} {result.get('snippet','')}"
    sim = similarity(source_text, target_text)
    score += int(sim * 55)
    comune = fold(item.get("comune", ""))
    if comune and comune in fold(target_text):
        score += 15
    for addr in address_hints:
        if fold(addr) in fold(target_text):
            score += 30
            break
    if norm(item.get("url", "")) == norm(result.get("url", "")):
        score = 100
    return min(score, 100)


def dedupe_contacts(contacts):
    best = {}
    rank = {"HIGH": 3, "MEDIUM": 2, "REVIEW": 1}
    for c in contacts:
        k = (c.get("type"), c.get("value"))
        if k not in best or rank.get(c.get("confidence"), 0) > rank.get(best[k].get("confidence"), 0):
            best[k] = c
    return list(best.values())


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_portal_domains():
    out = set()
    if not PORTALS.exists():
        return out
    with PORTALS.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            d = (row.get("domain") or "").lower().strip()
            d = d.removeprefix("*.").removeprefix("www.")
            if d:
                out.add(d)
    return out


state = load_json(STATE, {"items": {}})
items = state.get("items") or {}
known_domains = load_portal_domains()

candidates = sorted(
    items.items(),
    key=lambda kv: (
        0 if kv[1].get("lifecycle") == "NEW" else 1,
        -int(kv[1].get("score") or 0),
    ),
)
candidates = [
    (item_id, x) for item_id, x in candidates
    if x.get("lifecycle") == "NEW" or int(x.get("score") or 0) >= MIN_SCORE
][:MAX_ITEMS]

out_rows = []

for idx, (item_id, x) in enumerate(candidates, 1):
    listing_url = norm(x.get("url", ""))
    comune = (x.get("comune") or "").strip()
    title = clean(x.get("title") or "")
    snippet = clean(x.get("snippet") or "")
    source_text = f"{title} {snippet}"

    enrichment = {
        "checked_at": now(),
        "listing_fetch": {"ok": False, "status": 0, "error": ""},
        "address_hints": extract_addresses(source_text),
        "seller_name": "",
        "cross_matches": [],
        "public_contacts": [],
        "review_candidates": [],
        "queries": [],
    }

    if listing_url:
        ok, status, raw, error = fetch(listing_url)
        enrichment["listing_fetch"] = {"ok": ok, "status": status, "error": error}
        if ok and raw:
            page_text = clean(raw)
            enrichment["address_hints"] = list(dict.fromkeys(
                enrichment["address_hints"] + extract_addresses(page_text)
            ))[:5]
            enrichment["seller_name"] = extract_seller_name(raw)
            enrichment["public_contacts"].extend(
                extract_contacts(raw, listing_url, "LISTING_ORIGINALE", "HIGH")
            )

    title_query = f'"{title[:110]}" "{comune}"' if title else f'"{comune}" vendita immobile'
    queries = [title_query]
    if enrichment["address_hints"]:
        queries.append(
            f'"{enrichment["address_hints"][0]}" "{comune}" (vendita OR appartamento OR casa OR villa)'
        )

    seen_results = set()
    for q in queries[:2]:
        enrichment["queries"].append(q)
        results, _meta = bing_rss(q)
        for r in results:
            u = norm(r["url"])
            if not u or u in seen_results or u == listing_url:
                continue
            seen_results.add(u)
            mscore = same_property_score(x, r, enrichment["address_hints"])
            if mscore < 35:
                continue

            match = {
                "url": u,
                "title": r["title"],
                "snippet": r["snippet"],
                "host": source_host(u),
                "match_score": mscore,
                "contact_scan": "NOT_SCANNED",
            }

            if portal_like(u) and mscore >= 55:
                ok2, status2, raw2, error2 = fetch(u)
                match["contact_scan"] = "OK" if ok2 else f"HTTP_{status2 or 0}"
                if ok2 and raw2:
                    conf = "HIGH" if mscore >= 75 else "MEDIUM"
                    enrichment["public_contacts"].extend(
                        extract_contacts(raw2, u, "CROSS_MATCH_IMMOBILE", conf)
                    )
                    if not enrichment["seller_name"]:
                        enrichment["seller_name"] = extract_seller_name(raw2)
            enrichment["cross_matches"].append(match)

    enrichment["cross_matches"] = sorted(
        enrichment["cross_matches"], key=lambda z: z["match_score"], reverse=True
    )[:12]

    seller_name = enrichment["seller_name"]
    if seller_name:
        dq = f'site:paginebianche.it "{seller_name}" "{comune}"'
        enrichment["queries"].append(dq)
        results, _meta = bing_rss(dq, count=5)
        for r in results:
            if not directory_like(r["url"]):
                continue
            t = fold(f"{r['title']} {r['snippet']}")
            if fold(seller_name) not in t or (comune and fold(comune) not in t):
                continue
            ok3, status3, raw3, error3 = fetch(r["url"])
            contacts = []
            if ok3 and raw3 and fold(seller_name) in fold(raw3) and fold(comune) in fold(raw3):
                contacts = extract_contacts(
                    raw3, r["url"], "DIRECTORY_PUBBLICA_DA_VERIFICARE", "REVIEW"
                )
            enrichment["review_candidates"].append({
                "url": r["url"],
                "title": r["title"],
                "status": status3,
                "contacts": contacts,
                "note": "Verifica manuale identità prima di qualsiasi contatto commerciale.",
            })

    enrichment["public_contacts"] = dedupe_contacts(enrichment["public_contacts"])
    ready_contacts = [
        c for c in enrichment["public_contacts"]
        if c.get("confidence") in {"HIGH", "MEDIUM"}
    ]
    enrichment["contact_ready"] = bool(ready_contacts)
    enrichment["contact_ready_count"] = len(ready_contacts)
    enrichment["cross_match_count"] = len(enrichment["cross_matches"])

    x["enrichment"] = enrichment

    for c in ready_contacts:
        out_rows.append({
            "ITEM_ID": item_id,
            "COMUNE": comune,
            "TITOLO": title,
            "TIPO": c.get("type", ""),
            "VALORE": c.get("value", ""),
            "CONFIDENZA": c.get("confidence", ""),
            "FONTE_TIPO": c.get("source_type", ""),
            "FONTE_URL": c.get("source_url", ""),
            "CROSS_MATCH": enrichment["cross_match_count"],
            "SELLER_NAME": seller_name,
            "CHECKED_AT": enrichment["checked_at"],
        })

    print(
        f"[{idx}/{len(candidates)}] {comune} | cross-match={enrichment['cross_match_count']} "
        f"| contatti_pronti={enrichment['contact_ready_count']}"
    )
    time.sleep(0.25)

state["items"] = items
state["enrichment_updated_at"] = now()
STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

out_fields = [
    "ITEM_ID","COMUNE","TITOLO","TIPO","VALORE","CONFIDENZA","FONTE_TIPO",
    "FONTE_URL","CROSS_MATCH","SELLER_NAME","CHECKED_AT"
]
with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=out_fields)
    w.writeheader()
    w.writerows(out_rows)

if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig", newline="") as f:
        queue_rows = list(csv.DictReader(f))
        base_fields = list(queue_rows[0].keys()) if queue_rows else []

    by_url = {norm(x.get("url", "")): x for x in items.values() if x.get("url")}
    extra_fields = [
        "CONTATTO_PRONTO","CONTATTI_PUBBLICI","FONTE_CONTATTO",
        "CROSS_MATCH","NOME_INSERZIONISTA","RICERCA_PUBBLICA"
    ]
    fields = base_fields or [
        "PRIORITA","SCORE","COMUNE","FONTE","TITOLO","PREZZO","PREZZO_PRECEDENTE",
        "RIBASSI","INDIZIO_INSERZIONISTA","STATO","PRIMA_RILEVAZIONE",
        "ULTIMO_CONTROLLO","MOTIVI","URL"
    ]
    fields = fields + [f for f in extra_fields if f not in fields]

    enriched_rows = []
    for r in queue_rows:
        item = by_url.get(norm(r.get("URL", "")), {})
        e = item.get("enrichment") or {}
        ready = [
            c for c in (e.get("public_contacts") or [])
            if c.get("confidence") in {"HIGH", "MEDIUM"}
        ]
        r["CONTATTO_PRONTO"] = "SI" if ready else "NO"
        r["CONTATTI_PUBBLICI"] = " | ".join(
            f"{c.get('type')}:{c.get('value')}" for c in ready[:4]
        )
        r["FONTE_CONTATTO"] = " | ".join(
            dict.fromkeys(c.get("source_url", "") for c in ready if c.get("source_url"))
        )
        r["CROSS_MATCH"] = str(e.get("cross_match_count") or 0)
        r["NOME_INSERZIONISTA"] = e.get("seller_name") or ""
        r["RICERCA_PUBBLICA"] = "ESEGUITA" if e else "NON_ESEGUITA"
        enriched_rows.append(r)

    with QUEUE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(enriched_rows)

print(f"Arricchimento completato: {len(candidates)} annunci analizzati, {len(out_rows)} contatti operativi.")
