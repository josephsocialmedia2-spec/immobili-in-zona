#!/usr/bin/env python3
import csv
import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SOURCES = ROOT / "sources.csv"
STATE = DATA / "state.json"
QUEUE = DATA / "work_queue.csv"
SOURCE_STATUS = DATA / "source_status.csv"
DASHBOARD = ROOT / "dashboard.html"

UA = "F1SellerRadar/3.1 (+property-market-monitor; no-contact-harvesting)"
TIMEOUT = 20
DELAY = 2
GLOBAL_DETAIL_LIMIT = 60
TRACKING_KEYS = {"gclid","fbclid","msclkid","ref","source"}

DATA.mkdir(parents=True, exist_ok=True)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def hid(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]

def norm_url(url):
    p = urlparse(url)
    q = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
         if not (k.lower().startswith("utm_") or k.lower() in TRACKING_KEYS)]
    return urlunparse((p.scheme,p.netloc,p.path,p.params,urlencode(q),''))

def fetch(url):
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "it-IT,it;q=0.9",
        "Accept": "text/html,application/xhtml+xml"
    })
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(1_500_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
            anti = bool(re.search(r"captcha|cf-chl-|challenge-platform|verify you are human|access denied", body, re.I))
            return {"ok": 200 <= r.status < 400 and not anti, "status": r.status, "body": body,
                    "error": "verifica umana / anti-bot" if anti else "", "antibot": anti}
    except HTTPError as e:
        return {"ok": False, "status": e.code, "body": "", "error": str(e), "antibot": False}
    except (URLError, TimeoutError, OSError) as e:
        return {"ok": False, "status": 0, "body": "", "error": str(e), "antibot": False}

robots_cache = {}

def robots_allowed(url):
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in robots_cache:
        rp = RobotFileParser()
        rp.set_url(base + "/robots.txt")
        try:
            rp.read()
            robots_cache[base] = rp
        except Exception:
            robots_cache[base] = None
    rp = robots_cache[base]
    if rp is None:
        return False, "robots.txt non verificabile"
    try:
        return rp.can_fetch(UA, url), "robots.txt"
    except Exception:
        return False, "errore robots.txt"

def title_of(body):
    patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
        r'<title[^>]*>(.*?)</title>'
    ]
    for pat in patterns:
        m = re.search(pat, body, re.I|re.S)
        if m:
            return re.sub(r"\s+"," ", html.unescape(re.sub(r"<[^>]+>"," ",m.group(1)))).strip()[:220]
    return ""

def parse_price(raw):
    s = re.sub(r"\s+","", raw or "")
    if re.fullmatch(r"\d{4,8}(?:[.,]\d{1,2})?", s):
        try:
            v = int(round(float(s.replace(",","."))))
            if 5000 <= v <= 20_000_000:
                return v
        except ValueError:
            pass
    digits = re.sub(r"\D","",s)
    if digits:
        v = int(digits)
        if 5000 <= v <= 20_000_000:
            return v
    return None

def price_of(body):
    pats = [
        r'"price"\s*:\s*"?([0-9]{4,8}(?:[.,][0-9]{1,2})?)"?',
        r'(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\'][^>]+content=["\']([0-9.,\s]+)["\']',
        r'€\s*([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})',
        r'([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})\s*€'
    ]
    for pat in pats:
        for m in re.finditer(pat, body, re.I|re.S):
            v = parse_price(m.group(1))
            if v:
                return v
    return None

def text_of(body):
    x = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>"," ",body,flags=re.I)
    x = re.sub(r"<[^>]+>"," ",x)
    return re.sub(r"\s+"," ",html.unescape(x)).strip()[:250000]

def seller_hint(body):
    if re.search(r'("sellerType"|"publisherType"|"inserzionistaTipo")\s*:\s*["\']?(private|privato)',body,re.I):
        return "INDIZIO_PRIVATO"
    if re.search(r'("sellerType"|"publisherType"|"inserzionistaTipo")\s*:\s*["\']?(agency|agenzia)',body,re.I):
        return "INDIZIO_AGENZIA"
    t = text_of(body)
    if re.search(r"\b(pubblicato|inserito)\s+da\s+(un\s+)?privato\b|\bannuncio\s+privato\b",t,re.I):
        return "INDIZIO_PRIVATO"
    if re.search(r"\bagenzia immobiliare\b|\baffiliato tecnocasa\b|\btempocasa\b|\bgabetti\b|\bre/?max\b|\btecnorete\b",t,re.I):
        return "INDIZIO_AGENZIA"
    return "NON_DETERMINATO"

def extract_links(body, seed, host, pattern, limit):
    out, seen = [], set()
    for href in re.findall(r'href\s*=\s*["\']([^"\']+)["\']',body,re.I):
        u = norm_url(urljoin(seed, href))
        p = urlparse(u)
        if p.scheme not in ("http","https") or p.netloc != host:
            continue
        if pattern and not re.search(pattern,u):
            continue
        if u not in seen:
            seen.add(u); out.append(u)
        if len(out) >= limit:
            break
    return out

def drops(hist):
    return sum(1 for a,b in zip(hist,hist[1:]) if a.get("price") and b.get("price") and b["price"] < a["price"])

def score_item(item):
    s, why = 20, []
    if item.get("lifecycle") == "NEW":
        s += 15; why.append("nuovo annuncio")
    if item.get("seller_hint") == "INDIZIO_PRIVATO":
        s += 20; why.append("indizio privato da verificare")
    try:
        age = (datetime.now(timezone.utc)-datetime.fromisoformat(item["first_seen"])).days
        if age >= 30: s += 10; why.append("30+ giorni monitorati")
        if age >= 60: s += 10; why.append("60+ giorni monitorati")
    except Exception:
        pass
    d = drops(item.get("price_history",[]))
    if d >= 1: s += 15; why.append("ribasso prezzo")
    if d >= 2: s += 10; why.append("ribassi multipli")
    if item.get("http_status") in (404,410):
        s = min(s,15); why.append("annuncio non disponibile")
    return min(s,100), why or ["monitoraggio base"]

state = {"items":{}, "sources":{}}
if STATE.exists():
    try:
        state.update(json.loads(STATE.read_text(encoding="utf-8")))
    except Exception:
        pass

items = state.setdefault("items",{})
src_state = state.setdefault("sources",{})

with SOURCES.open(encoding="utf-8-sig", newline="") as f:
    sources = [r for r in csv.DictReader(f) if r.get("enabled")=="1" and r.get("seed_url")]

detail_total = 0
for src in sources:
    key = hid(src["seed_url"])
    check_hours = int(src.get("check_hours") or 6)
    old = src_state.get(key,{})
    if old.get("last_check"):
        try:
            elapsed = (datetime.now(timezone.utc)-datetime.fromisoformat(old["last_check"])).total_seconds()/3600
            if elapsed < check_hours:
                continue
        except Exception:
            pass

    allowed, reason = robots_allowed(src["seed_url"])
    if not allowed:
        src_state[key] = {**src, "last_check":now_iso(),"status":"ROBOTS_BLOCK","message":reason,"discovered":0}
        continue

    seed = fetch(src["seed_url"])
    if not seed["ok"]:
        status = "HUMAN_CHECK" if seed["antibot"] else "ERROR"
        src_state[key] = {**src,"last_check":now_iso(),"status":status,"message":seed["error"],"discovered":0}
        continue

    links = extract_links(seed["body"],src["seed_url"],src["allowed_host"],src["link_regex"],int(src.get("max_links") or 40))
    src_state[key] = {**src,"last_check":now_iso(),"status":"OK","message":"","discovered":len(links)}
    now = now_iso()

    new_urls = []
    for u in links:
        i = hid(u)
        if i not in items:
            items[i] = {"id":i,"comune":src["comune"],"fonte":src["fonte"],"source_key":key,"url":u,
                        "title":"","price_history":[],"seller_hint":"NON_DETERMINATO","first_seen":now,
                        "last_discovered":now,"last_checked":None,"checks":0,"lifecycle":"NEW",
                        "http_status":0,"last_error":"","score":0,"score_reasons":[]}
            new_urls.append(u)
        else:
            items[i]["last_discovered"] = now

    existing = sorted((x for x in items.values() if x.get("source_key")==key),
                      key=lambda x: x.get("last_checked") or "")
    candidates = list(dict.fromkeys(new_urls + [x["url"] for x in existing]))
    max_details = int(src.get("max_detail_checks") or 15)

    for u in candidates[:max_details]:
        if detail_total >= GLOBAL_DETAIL_LIMIT:
            break
        allowed, reason = robots_allowed(u)
        i = hid(u); item = items[i]
        item["last_checked"] = now_iso(); item["checks"] = int(item.get("checks",0))+1
        if not allowed:
            item["lifecycle"]="ROBOTS_BLOCK"; item["last_error"]=reason; item["http_status"]=0
        else:
            d = fetch(u); item["http_status"]=d["status"]; item["last_error"]=d["error"]
            if d["ok"]:
                t = title_of(d["body"])
                if t: item["title"]=t
                p = price_of(d["body"])
                if p and (not item["price_history"] or item["price_history"][-1]["price"] != p):
                    item["price_history"].append({"at":now_iso(),"price":p})
                    item["price_history"] = item["price_history"][-20:]
                item["seller_hint"] = seller_hint(d["body"])
                if item["lifecycle"]=="NEW" and item["checks"]>1:
                    item["lifecycle"]="TRACKED"
            elif d["antibot"]:
                item["lifecycle"]="HUMAN_CHECK"
            elif d["status"] in (404,410):
                item["lifecycle"]="NOT_AVAILABLE"
        item["score"],item["score_reasons"]=score_item(item)
        detail_total += 1
        time.sleep(DELAY)
    time.sleep(DELAY)

for item in items.values():
    item["score"],item["score_reasons"]=score_item(item)

STATE.write_text(json.dumps({"updated_at":now_iso(),"items":items,"sources":src_state},ensure_ascii=False,indent=2),encoding="utf-8")

rows=[]
for x in sorted(items.values(), key=lambda z:z.get("score",0), reverse=True):
    hist=x.get("price_history",[])
    rows.append({
        "PRIORITA":"ALTA" if x["score"]>=75 else "MEDIA" if x["score"]>=50 else "BASSA",
        "SCORE":x["score"],"COMUNE":x["comune"],"FONTE":x["fonte"],"TITOLO":x.get("title",""),
        "PREZZO":hist[-1]["price"] if hist else "","PREZZO_PRECEDENTE":hist[-2]["price"] if len(hist)>1 else "",
        "RIBASSI":drops(hist),"INDIZIO_INSERZIONISTA":x.get("seller_hint","NON_DETERMINATO"),
        "STATO":x.get("lifecycle",""),"PRIMA_RILEVAZIONE":x.get("first_seen",""),
        "ULTIMO_CONTROLLO":x.get("last_checked",""),"MOTIVI":" | ".join(x.get("score_reasons",[])),"URL":x["url"]
    })

fields=list(rows[0].keys()) if rows else ["PRIORITA","SCORE","COMUNE","FONTE","TITOLO","PREZZO","PREZZO_PRECEDENTE","RIBASSI","INDIZIO_INSERZIONISTA","STATO","PRIMA_RILEVAZIONE","ULTIMO_CONTROLLO","MOTIVI","URL"]
with QUEUE.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

src_rows=[]
for s in src_state.values():
    src_rows.append({"FONTE":s.get("fonte",""),"COMUNE":s.get("comune",""),"STATO":s.get("status",""),
                     "ULTIMO_CONTROLLO":s.get("last_check",""),"LINK_SCOPERTI":s.get("discovered",0),
                     "MESSAGGIO":s.get("message",""),"URL_SORGENTE":s.get("seed_url","")})
with SOURCE_STATUS.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["FONTE","COMUNE","STATO","ULTIMO_CONTROLLO","LINK_SCOPERTI","MESSAGGIO","URL_SORGENTE"])
    w.writeheader(); w.writerows(src_rows)

def euro(v):
    return "—" if not v else f"€ {int(v):,}".replace(",",".")

high=sum(1 for r in rows if int(r["SCORE"])>=75 and r["STATO"] not in ("NOT_AVAILABLE","ROBOTS_BLOCK"))
priv=sum(1 for r in rows if r["INDIZIO_INSERZIONISTA"]=="INDIZIO_PRIVATO")
ok=sum(1 for r in src_rows if r["STATO"]=="OK")

tr=[]
for r in rows:
    cls="high" if r["SCORE"]>=75 else "med" if r["SCORE"]>=50 else "low"
    prev=f" ↓ da {euro(r['PREZZO_PRECEDENTE'])}" if r["PREZZO"] and r["PREZZO_PRECEDENTE"] and int(r["PREZZO"])<int(r["PREZZO_PRECEDENTE"]) else ""
    tr.append(f"<tr><td><span class='score {cls}'>{r['SCORE']}</span></td><td>{html.escape(r['PRIORITA'])}</td><td>{html.escape(r['COMUNE'])}</td><td>{html.escape(r['INDIZIO_INSERZIONISTA'])}</td><td>{html.escape(r['TITOLO'])}</td><td>{euro(r['PREZZO'])}{html.escape(prev)}</td><td>{r['RIBASSI']}</td><td>{html.escape(r['STATO'])}</td><td>{html.escape(r['MOTIVI'])}</td><td><a href='{html.escape(r['URL'])}' target='_blank'>APRI E VERIFICA</a></td></tr>")
if not tr:
    tr=["<tr><td colspan='10'>Nessuna opportunità ancora rilevata.</td></tr>"]

DASHBOARD.write_text(f"""<!doctype html><html lang='it'><meta charset='utf-8'><title>F1 Seller Radar AUTO</title>
<style>body{{font-family:Segoe UI,Arial;background:#0c0f0d;color:#eee;margin:22px}}.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}}.card{{background:#151a17;border:1px solid #2c3630;padding:14px 18px;border-radius:12px}}table{{width:100%;border-collapse:collapse;background:#141815}}th,td{{padding:9px;border-bottom:1px solid #2c332f;text-align:left;font-size:13px}}th{{background:#1c221e}}a{{color:#78e08f;font-weight:700}}.score{{padding:5px 7px;border-radius:8px;font-weight:800}}.high{{background:#5f2020}}.med{{background:#5d4b17}}.low{{background:#25442f}}.note{{border-left:4px solid #78e08f;padding:12px;background:#171b18}}</style>
<h1>F1 SELLER RADAR — AUTO</h1><div>Aggiornato: {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>
<div class='note'>Trova opportunità e indizi pubblici. INDIZIO_PRIVATO va verificato aprendo la fonte. Nessun telefono/email viene raccolto automaticamente.</div>
<div class='cards'><div class='card'>Opportunità: <b>{len(rows)}</b></div><div class='card'>Priorità alta: <b>{high}</b></div><div class='card'>Indizi privato: <b>{priv}</b></div><div class='card'>Sorgenti OK: <b>{ok}/{len(sources)}</b></div></div>
<h2>DA LAVORARE</h2><table><tr><th>Score</th><th>Priorità</th><th>Comune</th><th>Inserzionista</th><th>Immobile</th><th>Prezzo</th><th>Ribassi</th><th>Stato</th><th>Perché</th><th>Azione</th></tr>{''.join(tr)}</table>
""",encoding="utf-8")

print(f"F1 Seller Radar AUTO: {len(rows)} opportunità, {high} priorità alta, {detail_total} dettagli controllati.")
