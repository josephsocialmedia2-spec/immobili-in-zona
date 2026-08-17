#!/usr/bin/env python3
"""F1 Seller Radar — discovery via DuckDuckGo HTML.

Inserisce nello state.json gli annunci pubblici trovati sui portali configurati.
Il motore cloud_radar_v4.py continua poi a gestire scoring, storico, coda e dashboard.
"""
import csv, hashlib, html, json, re, time
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"; DATA.mkdir(parents=True, exist_ok=True)
MUNICIPALITIES = ROOT / "municipalities.csv"
PORTALS = ROOT / "portal_catalog.csv"
STATE = DATA / "state.json"
STATUS = DATA / "ddg_source_status.csv"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
TIMEOUT = 20
TRACK = {"gclid","fbclid","msclkid","ref","source"}
PROPERTY_WORDS = (
    "casa","appartamento","villa","villetta","trilocale","bilocale","quadrilocale",
    "immobile","terratetto","monolocale","rustico","attico","alloggio","vendita",
    "vendesi","house","property"
)
SALE_WORDS = ("vendita","vendesi","vende","in vendita","€","euro","for sale")

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self._href=None; self._attrs={}; self._text=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower()=="a":
            self._attrs=dict(attrs); self._href=self._attrs.get("href"); self._text=[]
    def handle_data(self, data):
        if self._href is not None: self._text.append(data)
    def handle_endtag(self, tag):
        if tag.lower()=="a" and self._href is not None:
            text=re.sub(r"\s+"," ",html.unescape("".join(self._text))).strip()
            self.links.append((self._href,text,self._attrs))
            self._href=None; self._text=[]; self._attrs={}

def now(): return datetime.now(timezone.utc).isoformat()
def key(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()[:20]
def clean(s): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",s or ""))).strip()
def fold(s): return clean(s).casefold()

def norm(url):
    p=urlparse(url)
    q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not (k.lower().startswith("utm_") or k.lower() in TRACK)]
    return urlunparse((p.scheme,p.netloc,p.path,p.params,urlencode(q),""))

def host_matches(host, expected):
    host=(host or "").lower().split(":")[0]; expected=(expected or "").lower().strip()
    if not expected: return True
    if expected.startswith("*."): return host.endswith(expected[1:])
    return host==expected or host.removeprefix("www.")==expected.removeprefix("www.")

def unwrap_ddg(href):
    if href.startswith("//"): href="https:"+href
    p=urlparse(href)
    if "duckduckgo.com" in p.netloc and p.path.startswith("/l/"):
        qs=parse_qs(p.query)
        if qs.get("uddg"): return unquote(qs["uddg"][0])
    return href

def search(query, count=12):
    data=urlencode({"q":query,"kl":"it-it"}).encode("utf-8")
    req=Request("https://html.duckduckgo.com/html/",data=data,headers={
        "User-Agent":UA,"Accept":"text/html,application/xhtml+xml","Accept-Language":"it-IT,it;q=0.9,en;q=0.5"
    })
    try:
        with urlopen(req,timeout=TIMEOUT) as r:
            body=r.read(1_500_000).decode(r.headers.get_content_charset() or "utf-8",errors="replace")
    except HTTPError as e:
        return [], f"HTTP {e.code}"
    except (URLError,TimeoutError,OSError) as e:
        return [], str(e)
    if re.search(r"captcha|verify you are human|anomaly|rate limit",body,re.I):
        return [], "verifica umana / rate limit"
    p=LinkParser(); p.feed(body)
    out=[]; seen=set()
    for href,text,attrs in p.links:
        if "result__a" not in attrs.get("class",""): continue
        u=norm(unwrap_ddg(href))
        if not u.startswith(("http://","https://")) or u in seen: continue
        if "duckduckgo.com/y.js" in u: continue
        seen.add(u); out.append({"url":u,"title":clean(text)})
        if len(out)>=count: break
    return out, ""

def relevant(url,title,comune,domain,path_regex):
    p=urlparse(url)
    if not host_matches(p.netloc,domain): return False
    if path_regex and not re.search(path_regex,p.path,re.I): return False
    t=fold(title); c=fold(comune)
    if c and c not in t and c.replace(" ","-") not in url.casefold(): return False
    if not any(w in t for w in PROPERTY_WORDS): return False
    if not any(w in t for w in SALE_WORDS): return False
    return True

def price(text):
    for pat in [r"€\s*([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})",r"([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})\s*€"]:
        m=re.search(pat,text,re.I)
        if m:
            n=int(re.sub(r"\D","",m.group(1)))
            if 5000<=n<=20000000: return n
    return None

def seller_hint(text):
    t=fold(text)
    if re.search(r"\b(no agenzie|senza agenzia|da privato|annuncio privato|inserzionista privato|vendita privata|privato vende|vendo privatamente|solo privati)\b",t,re.I): return "INDIZIO_PRIVATO"
    if re.search(r"\b(agenzia immobiliare|tecnocasa|tecnorete|tempocasa|gabetti|re/?max|franchising immobiliare)\b",t,re.I): return "INDIZIO_AGENZIA"
    return "NON_DETERMINATO"

def load_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))

municipalities=[r["comune"].strip() for r in load_csv(MUNICIPALITIES) if r.get("enabled")=="1" and r.get("comune")]
portals=[r for r in load_csv(PORTALS) if r.get("enabled")=="1" and r.get("query_template")]

try: state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"items":{}}
except Exception: state={"items":{}}
items=state.setdefault("items",{})
status_rows=[]; total_accepted=0

for comune in municipalities:
    for portal in portals:
        label=(portal.get("label") or "").strip()
        domain=(portal.get("domain") or "").strip()
        path_regex=(portal.get("path_regex") or "").strip()
        private_intent=portal.get("private_intent")=="1"
        max_results=int(portal.get("max_results") or 10)
        query=(portal.get("query_template") or "").replace("{comune}",comune)
        results,error=search(query,max_results)
        accepted=0
        for r in results:
            url,title=r["url"],r["title"]
            if not relevant(url,title,comune,domain,path_regex): continue
            i=key(url); p=price(title); hint=seller_hint(title)
            if i not in items:
                items[i]={
                    "id":i,"comune":comune,"fonte":label,"url":url,"title":title[:220],"snippet":"",
                    "price_history":[],"seller_hint":hint,"private_intent":private_intent,
                    "first_seen":now(),"last_seen":now(),"checks":1,"lifecycle":"NEW",
                    "domain_rule":domain,"path_rule":path_regex,"discovery_engine":"DUCKDUCKGO_HTML"
                }
            else:
                x=items[i]; x["last_seen"]=now(); x["checks"]=int(x.get("checks",0))+1
                x["title"]=title[:220] or x.get("title",""); x["private_intent"]=x.get("private_intent",False) or private_intent
                x["discovery_engine"]="DUCKDUCKGO_HTML"
                if hint!="NON_DETERMINATO": x["seller_hint"]=hint
                if x.get("lifecycle")=="NEW" and x["checks"]>1: x["lifecycle"]="TRACKED"
            if p:
                hist=items[i].setdefault("price_history",[])
                if not hist or hist[-1].get("price")!=p: hist.append({"at":now(),"price":p}); items[i]["price_history"]=hist[-20:]
            accepted+=1
        total_accepted+=accepted
        status_rows.append({
            "FONTE":label,"COMUNE":comune,"STATO":"OK" if not error else "ERROR",
            "ULTIMO_CONTROLLO":now(),"RISULTATI_GREZZI":len(results),"ACCETTATI":accepted,
            "MESSAGGIO":error,"QUERY":query
        })
        time.sleep(0.45)

state["items"]=items
state["ddg_updated_at"]=now()
STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
fields=["FONTE","COMUNE","STATO","ULTIMO_CONTROLLO","RISULTATI_GREZZI","ACCETTATI","MESSAGGIO","QUERY"]
with STATUS.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(status_rows)
print(f"F1 DDG Discovery: {total_accepted} accettati su {sum(int(r['RISULTATI_GREZZI']) for r in status_rows)} risultati grezzi / {len(status_rows)} query.")
