#!/usr/bin/env python3
"""F1 Seller Radar — discovery DuckDuckGo ottimizzata.

Riduce il carico: per ogni comune esegue ricerca generale + privati e alcune query mirate
sui portali principali. I risultati vengono ricondotti al catalogo portali per dominio.
"""
import csv, hashlib, html, json, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from search_engine import search

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"; DATA.mkdir(parents=True,exist_ok=True)
MUNICIPALITIES=ROOT/"municipalities.csv"
PORTALS=ROOT/"portal_catalog.csv"
STATE=DATA/"state.json"
STATUS=DATA/"ddg_source_status.csv"
TRACK={"gclid","fbclid","msclkid","ref","source"}
PROPERTY_WORDS=("casa","appartamento","villa","villetta","trilocale","bilocale","quadrilocale","immobile","terratetto","monolocale","rustico","attico","alloggio","vendita","vendesi","house","property")
SALE_WORDS=("vendita","vendesi","vende","in vendita","€","euro","for sale")
MAJOR={"Immobiliare.it","Idealista","Casa.it","Subito privati"}

def now(): return datetime.now(timezone.utc).isoformat()
def key(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()[:20]
def clean(s): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",s or ""))).strip()
def fold(s): return clean(s).casefold()
def norm(url):
    p=urlparse(url or ""); q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not(k.lower().startswith("utm_") or k.lower() in TRACK)]
    return urlunparse((p.scheme,p.netloc,p.path,p.params,urlencode(q),""))
def host_matches(host,expected):
    host=(host or "").lower().split(":")[0]; expected=(expected or "").lower().strip()
    if not expected: return True
    if expected.startswith("*."): return host.endswith(expected[1:])
    return host==expected or host.removeprefix("www.")==expected.removeprefix("www.")
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

def portal_for_url(url,portals):
    h=urlparse(url).netloc
    for p in portals:
        d=(p.get("domain") or "").strip()
        if d and host_matches(h,d): return p
    return None

def relevant(url,title,comune,portal=None):
    t=fold(title); c=fold(comune); p=urlparse(url)
    if portal:
        path_regex=(portal.get("path_regex") or "").strip()
        if path_regex and not re.search(path_regex,p.path,re.I): return False
    if c and c not in t and c.replace(" ","-") not in url.casefold(): return False
    if not any(w in t for w in PROPERTY_WORDS): return False
    if not any(w in t for w in SALE_WORDS): return False
    return True

def upsert(items,url,title,comune,label,private_intent,domain="",path_regex=""):
    i=key(url); p=price(title); hint=seller_hint(title)
    if i not in items:
        items[i]={"id":i,"comune":comune,"fonte":label,"url":url,"title":title[:220],"snippet":"","price_history":[],"seller_hint":hint,"private_intent":private_intent,"first_seen":now(),"last_seen":now(),"checks":1,"lifecycle":"NEW","domain_rule":domain,"path_rule":path_regex,"discovery_engine":"DUCKDUCKGO_HTML_V2"}
    else:
        x=items[i]; x["last_seen"]=now(); x["checks"]=int(x.get("checks",0))+1; x["title"]=title[:220] or x.get("title",""); x["private_intent"]=x.get("private_intent",False) or private_intent; x["discovery_engine"]="DUCKDUCKGO_HTML_V2"
        if hint!="NON_DETERMINATO": x["seller_hint"]=hint
        if x.get("lifecycle")=="NEW" and x["checks"]>1: x["lifecycle"]="TRACKED"
    if p:
        hist=items[i].setdefault("price_history",[])
        if not hist or hist[-1].get("price")!=p: hist.append({"at":now(),"price":p}); items[i]["price_history"]=hist[-20:]

municipalities=[r["comune"].strip() for r in load_csv(MUNICIPALITIES) if r.get("enabled")=="1" and r.get("comune")]
portals=[r for r in load_csv(PORTALS) if r.get("enabled")=="1"]
major=[p for p in portals if (p.get("label") or "").strip() in MAJOR]
try: state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"items":{}}
except Exception: state={"items":{}}
items=state.setdefault("items",{})
status=[]; total=0

for comune in municipalities:
    plans=[
        ("Web generale",f'"{comune}" (vendita OR "in vendita") (casa OR appartamento OR villa)',30,False,None),
        ("Web privati",f'"{comune}" ("privato vende" OR "no agenzie" OR "da privato") (casa OR appartamento OR villa)',20,True,None),
    ]
    for p in major:
        plans.append(((p.get("label") or "").strip(),(p.get("query_template") or "").replace("{comune}",comune),10,p.get("private_intent")=="1",p))
    for label,query,count,private_query,forced_portal in plans:
        results,error=search(query,count); accepted=0
        for r in results:
            url=norm(r.get("url",'')); title=clean(r.get("title",'')); portal=forced_portal or portal_for_url(url,portals)
            if forced_portal:
                d=(forced_portal.get("domain") or "").strip()
                if d and not host_matches(urlparse(url).netloc,d): continue
            if not relevant(url,title,comune,portal): continue
            actual_label=(portal.get("label") or "").strip() if portal else label
            private_intent=private_query or (portal is not None and portal.get("private_intent")=="1")
            upsert(items,url,title,comune,actual_label,private_intent,(portal.get("domain") or "") if portal else "",(portal.get("path_regex") or "") if portal else "")
            accepted+=1
        total+=accepted
        status.append({"FONTE":label,"COMUNE":comune,"STATO":"OK" if not error else "ERROR","ULTIMO_CONTROLLO":now(),"RISULTATI_GREZZI":len(results),"ACCETTATI":accepted,"MESSAGGIO":error,"QUERY":query})
        time.sleep(0.3)

state["items"]=items; state["ddg_updated_at"]=now(); STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
fields=["FONTE","COMUNE","STATO","ULTIMO_CONTROLLO","RISULTATI_GREZZI","ACCETTATI","MESSAGGIO","QUERY"]
with STATUS.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(status)
print(f"F1 DDG Discovery v2: {total} accettati / {sum(int(r['RISULTATI_GREZZI']) for r in status)} grezzi / {len(status)} query.")
