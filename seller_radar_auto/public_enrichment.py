#!/usr/bin/env python3
"""F1 Seller Radar: cross-match e arricchimento da fonti pubbliche."""
import csv, html, json, os, re, time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE = DATA / "state.json"
QUEUE = DATA / "work_queue.csv"
OUT = DATA / "public_enrichment.csv"

UA = "F1SellerRadar-Enrichment/1.1 (+public-source-crossmatch)"
TIMEOUT = 18
MAX_ITEMS = int(os.getenv("F1_ENRICH_MAX", "35"))
MAX_RESULTS = int(os.getenv("F1_ENRICH_RESULTS", "8"))
MIN_SCORE = int(os.getenv("F1_ENRICH_MIN_SCORE", "45"))
TRACK = {"gclid", "fbclid", "msclkid", "ref", "source"}

PHONE_RE = re.compile(r"(?<!\d)(?:\+39[\s.\-]?)?(?:0\d{1,3}[\s.\-]?\d{5,8}|3\d{2}[\s.\-]?\d{6,7})(?!\d)")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
ADDRESS_RE = re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s]{2,80}?\s+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|\s*[A-Za-z])?\b",
    re.I,
)
PORTAL_HINTS = (
    "immobiliare.it","idealista.it","casa.it","trovacasa.it","wikicasa.it","subito.it",
    "bakeca.it","trovit.it","nestoria.it","gate-away.com","venderecasa.com","tuttocasa.it",
    "tecnocasa.it","tecnorete.it","tempocasa.it","facebook.com"
)

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
    p = urlparse(url or "")
    q = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
         if not (k.lower().startswith("utm_") or k.lower() in TRACK)]
    return urlunparse((p.scheme,p.netloc,p.path,p.params,urlencode(q),""))

def host(url):
    return urlparse(url or "").netloc.lower().removeprefix("www.")

def fetch(url, accept="text/html,application/xhtml+xml,*/*"):
    req = Request(url, headers={"User-Agent":UA,"Accept":accept,"Accept-Language":"it-IT,it;q=0.9"})
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(1_200_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
            if re.search(r"captcha|verify you are human|access denied|robot check", body, re.I):
                return False, r.status, "", "verifica umana / anti-bot"
            return 200 <= r.status < 400, r.status, body, ""
    except HTTPError as e:
        return False, e.code, "", str(e)
    except (URLError, TimeoutError, OSError) as e:
        return False, 0, "", str(e)

def search(query, count=MAX_RESULTS):
    url = "https://www.bing.com/search?" + urlencode({"q":query,"format":"rss","count":str(count)})
    ok, status, body, err = fetch(url, "application/rss+xml,application/xml,text/xml,*/*")
    if not ok:
        return []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    out = []
    for n in root.findall(".//item")[:count]:
        u = norm((n.findtext("link") or "").strip())
        if u.startswith(("http://","https://")):
            out.append({
                "url":u,
                "title":clean(n.findtext("title") or "")[:240],
                "snippet":clean(n.findtext("description") or "")[:600],
            })
    return out

def addresses(text):
    out, seen = [], set()
    for m in ADDRESS_RE.finditer(clean(text)):
        v = re.sub(r"\s+", " ", m.group(0)).strip(" ,.;")
        if v.casefold() not in seen:
            seen.add(v.casefold()); out.append(v[:140])
    return out[:5]

def seller_name(raw):
    patterns = [
        r'"seller"\s*:\s*\{[^{}]{0,500}?"name"\s*:\s*"([^"]{3,100})"',
        r'"agent"\s*:\s*\{[^{}]{0,500}?"name"\s*:\s*"([^"]{3,100})"',
        r'(?:inserzionista|venditore|proprietario)\s*[:\-]\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ\'’\-]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ\'’\-]+){1,3})',
    ]
    for p in patterns:
        m = re.search(p, raw or "", re.I | re.S)
        if m:
            v = clean(m.group(1))
            if 3 <= len(v) <= 100:
                return v
    return ""

def contacts(text, url, source_type, confidence):
    plain, out, seen = clean(text), [], set()
    for m in PHONE_RE.finditer(plain):
        v = re.sub(r"\D", "", m.group(0))
        if v.startswith("39") and len(v) >= 11:
            v = "+" + v
        if not 9 <= len(re.sub(r"\D","",v)) <= 13:
            continue
        k = ("PHONE",v)
        if k not in seen:
            seen.add(k); out.append({"type":"PHONE","value":v,"source_url":url,"source_type":source_type,"confidence":confidence})
    for m in EMAIL_RE.finditer(plain):
        v = m.group(0).lower()
        if v.endswith((".png",".jpg",".jpeg",".webp",".gif")):
            continue
        k = ("EMAIL",v)
        if k not in seen:
            seen.add(k); out.append({"type":"EMAIL","value":v,"source_url":url,"source_type":source_type,"confidence":confidence})
    return out[:12]

def portal(url):
    h = host(url)
    return any(h == d or h.endswith("." + d) for d in PORTAL_HINTS)

def tokens(text):
    stop = {"della","delle","degli","dello","alla","alle","con","per","vendita","casa","appartamento","immobile","villa","torino","euro","privato"}
    return {t for t in re.findall(r"[a-zà-ÿ0-9]{3,}", fold(text)) if t not in stop}

def match_score(item, result, addr):
    a = tokens(f"{item.get('title','')} {item.get('snippet','')}")
    b = tokens(f"{result.get('title','')} {result.get('snippet','')}")
    sim = len(a & b) / len(a | b) if a and b else 0
    s = int(sim * 55)
    if fold(item.get("comune","")) in fold(f"{result.get('title','')} {result.get('snippet','')}"):
        s += 15
    if any(fold(x) in fold(f"{result.get('title','')} {result.get('snippet','')}") for x in addr):
        s += 30
    return min(s,100)

def dedupe(cs):
    rank = {"HIGH":3,"MEDIUM":2,"REVIEW":1}
    out = {}
    for c in cs:
        k = (c.get("type"),c.get("value"))
        if k not in out or rank.get(c.get("confidence"),0) > rank.get(out[k].get("confidence"),0):
            out[k] = c
    return list(out.values())

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default

state = load_json(STATE, {"items":{}})
items = state.get("items") or {}
candidates = sorted(
    items.items(),
    key=lambda kv: (0 if kv[1].get("lifecycle") == "NEW" else 1, -int(kv[1].get("score") or 0))
)
candidates = [(i,x) for i,x in candidates if x.get("lifecycle") == "NEW" or int(x.get("score") or 0) >= MIN_SCORE][:MAX_ITEMS]
out_rows = []

for pos, (item_id, x) in enumerate(candidates, 1):
    url = norm(x.get("url",""))
    comune = (x.get("comune") or "").strip()
    title = clean(x.get("title") or "")
    snippet = clean(x.get("snippet") or "")
    private_candidate = (
        x.get("seller_hint") == "INDIZIO_PRIVATO" or bool(x.get("private_intent"))
    ) and x.get("seller_hint") != "INDIZIO_AGENZIA"

    e = {
        "checked_at":now(),
        "private_candidate":private_candidate,
        "listing_fetch":{"ok":False,"status":0,"error":""},
        "address_hints":addresses(f"{title} {snippet}"),
        "seller_name":"",
        "cross_matches":[],
        "public_contacts":[],
        "review_candidates":[],
        "queries":[],
    }

    if url:
        ok, status, raw, err = fetch(url)
        e["listing_fetch"] = {"ok":ok,"status":status,"error":err}
        if ok and raw:
            e["address_hints"] = list(dict.fromkeys(e["address_hints"] + addresses(raw)))[:5]
            e["seller_name"] = seller_name(raw)
            if private_candidate:
                e["public_contacts"] += contacts(raw, url, "LISTING_ORIGINALE", "HIGH")

    queries = [f'"{title[:110]}" "{comune}"' if title else f'"{comune}" vendita immobile']
    if e["address_hints"]:
        queries.append(f'"{e["address_hints"][0]}" "{comune}" (vendita OR appartamento OR casa OR villa)')

    seen = set()
    for q in queries[:2]:
        e["queries"].append(q)
        for r in search(q):
            u = r["url"]
            if u == url or u in seen:
                continue
            seen.add(u)
            ms = match_score(x, r, e["address_hints"])
            if ms < 35:
                continue
            m = {"url":u,"title":r["title"],"snippet":r["snippet"],"host":host(u),"match_score":ms,"contact_scan":"NOT_SCANNED"}
            if private_candidate and portal(u) and ms >= 55:
                ok2, st2, raw2, er2 = fetch(u)
                m["contact_scan"] = "OK" if ok2 else f"HTTP_{st2 or 0}"
                if ok2 and raw2:
                    conf = "HIGH" if ms >= 75 else "MEDIUM"
                    e["public_contacts"] += contacts(raw2, u, "CROSS_MATCH_IMMOBILE", conf)
                    if not e["seller_name"]:
                        e["seller_name"] = seller_name(raw2)
            e["cross_matches"].append(m)

    e["cross_matches"] = sorted(e["cross_matches"], key=lambda z:z["match_score"], reverse=True)[:12]

    # PagineBianche: solo con nome inserzionista esplicito; risultati sempre da verificare.
    if private_candidate and e["seller_name"]:
        q = f'site:paginebianche.it "{e["seller_name"]}" "{comune}"'
        e["queries"].append(q)
        for r in search(q, 5):
            if "paginebianche.it" not in host(r["url"]):
                continue
            text = fold(f"{r['title']} {r['snippet']}")
            if fold(e["seller_name"]) not in text or (comune and fold(comune) not in text):
                continue
            ok3, st3, raw3, er3 = fetch(r["url"])
            cs = []
            if ok3 and raw3 and fold(e["seller_name"]) in fold(raw3) and fold(comune) in fold(raw3):
                cs = contacts(raw3, r["url"], "DIRECTORY_PUBBLICA_DA_VERIFICARE", "REVIEW")
            e["review_candidates"].append({
                "url":r["url"],"title":r["title"],"status":st3,"contacts":cs,
                "note":"Verifica manuale identità prima di qualsiasi contatto commerciale."
            })

    e["public_contacts"] = dedupe(e["public_contacts"])
    ready = [c for c in e["public_contacts"] if c.get("confidence") in {"HIGH","MEDIUM"}]
    e["contact_ready"] = bool(ready)
    e["contact_ready_count"] = len(ready)
    e["cross_match_count"] = len(e["cross_matches"])
    x["enrichment"] = e

    for c in ready:
        out_rows.append({
            "ITEM_ID":item_id,"COMUNE":comune,"TITOLO":title,"TIPO":c.get("type",""),
            "VALORE":c.get("value",""),"CONFIDENZA":c.get("confidence",""),
            "FONTE_TIPO":c.get("source_type",""),"FONTE_URL":c.get("source_url",""),
            "CROSS_MATCH":e["cross_match_count"],"SELLER_NAME":e["seller_name"],"CHECKED_AT":e["checked_at"],
        })
    print(f"[{pos}/{len(candidates)}] {comune} | privato={private_candidate} | cross={e['cross_match_count']} | contatti={len(ready)}")
    time.sleep(0.25)

state["items"] = items
state["enrichment_updated_at"] = now()
STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

out_fields = ["ITEM_ID","COMUNE","TITOLO","TIPO","VALORE","CONFIDENZA","FONTE_TIPO","FONTE_URL","CROSS_MATCH","SELLER_NAME","CHECKED_AT"]
with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=out_fields); w.writeheader(); w.writerows(out_rows)

if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else [
            "PRIORITA","SCORE","COMUNE","FONTE","TITOLO","PREZZO","PREZZO_PRECEDENTE","RIBASSI",
            "INDIZIO_INSERZIONISTA","STATO","PRIMA_RILEVAZIONE","ULTIMO_CONTROLLO","MOTIVI","URL"
        ]
    extras = ["CONTATTO_PRONTO","CONTATTI_PUBBLICI","FONTE_CONTATTO","CROSS_MATCH","NOME_INSERZIONISTA","RICERCA_PUBBLICA"]
    fields += [k for k in extras if k not in fields]
    by_url = {norm(x.get("url","")):x for x in items.values() if x.get("url")}
    for r in rows:
        item = by_url.get(norm(r.get("URL","")), {})
        e = item.get("enrichment") or {}
        ready = [c for c in (e.get("public_contacts") or []) if c.get("confidence") in {"HIGH","MEDIUM"}]
        r["CONTATTO_PRONTO"] = "SI" if ready else "NO"
        r["CONTATTI_PUBBLICI"] = " | ".join(f"{c.get('type')}:{c.get('value')}" for c in ready[:4])
        r["FONTE_CONTATTO"] = " | ".join(dict.fromkeys(c.get("source_url","") for c in ready if c.get("source_url")))
        r["CROSS_MATCH"] = str(e.get("cross_match_count") or 0)
        r["NOME_INSERZIONISTA"] = e.get("seller_name") or ""
        r["RICERCA_PUBBLICA"] = "ESEGUITA" if e else "NON_ESEGUITA"
    with QUEUE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

print(f"Arricchimento completato: {len(candidates)} annunci, {len(out_rows)} contatti operativi.")
