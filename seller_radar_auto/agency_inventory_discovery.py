#!/usr/bin/env python3
from __future__ import annotations
import csv, datetime as dt, html, json, re, urllib.parse, urllib.request
from html.parser import HTMLParser
from pathlib import Path
from search_engine import search

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
AGENCIES=ROOT/"agencies.csv"
QUEUE=DATA/"work_queue.csv"
OUT=DATA/"agency_inventory_candidates.csv"
UA="Mozilla/5.0 (compatible; F1SellerRadar/1.0; public agency inventory research)"
TODAY=dt.date.today().isoformat()

SALE_WORDS=("vendita","immobile","immobili","appartamento","villa","casa","rustico","terreno","box","locale","negozio","capannone","property","proprieta")
SKIP_WORDS=("privacy","cookie","contatti","chi-siamo","about","login","account","facebook.com","instagram.com","linkedin.com","youtube.com","mailto:","tel:")

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.href=None; self.buf=[]; self.items=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a":
            self.href=dict(attrs).get("href"); self.buf=[]
    def handle_data(self,data):
        if self.href is not None: self.buf.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=="a" and self.href is not None:
            self.items.append((self.href," ".join(" ".join(self.buf).split())))
            self.href=None; self.buf=[]

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept-Language":"it-IT,it;q=0.9"})
    with urllib.request.urlopen(req,timeout=25) as r:
        return r.read().decode("utf-8","replace")

def norm_url(u):
    try:
        p=urllib.parse.urlsplit(u.strip())
        return urllib.parse.urlunsplit((p.scheme.lower(),p.netloc.lower(),re.sub(r"/+$","",p.path),"",""))
    except Exception:return (u or "").strip()

def price(text):
    m=re.search(r"€\s*([0-9][0-9. ]{2,})",text or "")
    if not m:return ""
    return re.sub(r"[^0-9]","",m.group(1))

def load_places():
    vals=[]
    for p in [DATA/"municipalities_operational.csv",ROOT/"municipalities.csv"]:
        if p.exists():
            with p.open(encoding="utf-8-sig",newline="") as f:
                for r in csv.DictReader(f):
                    if str(r.get("enabled","")).strip()=="1":
                        v=(r.get("comune") or "").strip()
                        if v and v not in vals: vals.append(v)
            break
    lp=ROOT/"territory_localities.csv"
    if lp.exists():
        with lp.open(encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f):
                if str(r.get("enabled","")).strip()=="1":
                    v=(r.get("localita") or "").strip()
                    if v and v not in vals: vals.append(v)
    return sorted(vals,key=len,reverse=True)

PLACES=load_places()
def infer_place(text, fallback=""):
    low=(text or "").casefold()
    for p in PLACES:
        if p.casefold() in low:
            return p
    return fallback

rows=[]; seen=set()
with AGENCIES.open(encoding="utf-8-sig",newline="") as f:
    agencies=[r for r in csv.DictReader(f) if str(r.get("enabled","")).strip()=="1"]

for a in agencies:
    name=(a.get("agency") or "").strip(); base=(a.get("comune") or "").strip()
    inv=(a.get("inventory_url") or "").strip(); web=(a.get("website") or "").strip()
    candidates=[]
    queries=[f'"{name}" vendita immobili']
    dom=urllib.parse.urlsplit(web or inv).netloc
    if dom: queries.append(f'site:{dom} vendita immobile')
    for q in queries:
        for x in search(q,limit=25,delay=.2):
            candidates.append((x.get("url",""),x.get("title",""),x.get("snippet",""),q))
    if inv:
        try:
            raw=get(inv); parser=Links(); parser.feed(raw)
            for href,txt in parser.items:
                u=urllib.parse.urljoin(inv,html.unescape(href or ""))
                blob=(u+" "+txt).lower()
                if any(s in blob for s in SKIP_WORDS): continue
                if any(k in blob for k in SALE_WORDS) or "€" in txt:
                    candidates.append((u,txt,"","DIRECT_CRAWL"))
        except Exception:
            pass
    for u,title,snip,q in candidates:
        u=norm_url(u)
        if not u or u in seen or not u.startswith(("http://","https://")): continue
        seen.add(u)
        blob=" ".join([title or "",snip or "",u])
        comune=infer_place(blob,base)
        rows.append({
            "AGENCY":name,"COMUNE":comune,"TITOLO":title or name,
            "PREZZO":price(blob),"URL":u,"QUERY":q,"FIRST_SEEN":TODAY,"LAST_SEEN":TODAY
        })

DATA.mkdir(exist_ok=True)
fields=["AGENCY","COMUNE","TITOLO","PREZZO","URL","QUERY","FIRST_SEEN","LAST_SEEN"]
with OUT.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

old=[]; old_fields=[]
if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f); old=list(reader); old_fields=list(reader.fieldnames or [])
byurl={norm_url(r.get("URL","")):r for r in old if r.get("URL")}
for x in rows:
    key=norm_url(x["URL"])
    if key in byurl:
        byurl[key]["ULTIMO_CONTROLLO"]=TODAY
        if not byurl[key].get("PREZZO") and x.get("PREZZO"): byurl[key]["PREZZO"]=x["PREZZO"]
        continue
    rec={
        "PRIORITA":"MEDIA","SCORE":"25","TIPO_OPPORTUNITA":"AGENCY_LISTING",
        "TARGET":"IMMOBILE","FASE_PROGETTO":"","OBIETTIVO_COMMERCIALE":"MONITORAGGIO ACQUISIZIONE",
        "COMUNE":x["COMUNE"],"FONTE":x["AGENCY"],"TITOLO":x["TITOLO"],"PREZZO":x["PREZZO"],
        "PREZZO_PRECEDENTE":"","RIBASSI":"0","INDIZIO_INSERZIONISTA":"AGENZIA",
        "STATO":"NEW","PRIMA_RILEVAZIONE":TODAY,"ULTIMO_CONTROLLO":TODAY,
        "MOTIVI":"inventario agenzia pubblico","PDF_DA_VERIFICARE":"","URL":x["URL"],
        "CONTATTO_PRONTO":"NO","CONTATTI_PUBBLICI":"","FONTE_CONTATTO":"","CROSS_MATCH":"0",
        "NOME_INSERZIONISTA":x["AGENCY"],"RICERCA_PUBBLICA":x["QUERY"],
        "VIA_RADAR":"","INDIRIZZI_ZONA":"","AZIONE_ZONA":""
    }
    old.append(rec); byurl[key]=rec

default_fields=["PRIORITA","SCORE","TIPO_OPPORTUNITA","TARGET","FASE_PROGETTO","OBIETTIVO_COMMERCIALE","COMUNE","FONTE","TITOLO","PREZZO","PREZZO_PRECEDENTE","RIBASSI","INDIZIO_INSERZIONISTA","STATO","PRIMA_RILEVAZIONE","ULTIMO_CONTROLLO","MOTIVI","PDF_DA_VERIFICARE","URL","CONTATTO_PRONTO","CONTATTI_PUBBLICI","FONTE_CONTATTO","CROSS_MATCH","NOME_INSERZIONISTA","RICERCA_PUBBLICA","VIA_RADAR","INDIRIZZI_ZONA","AZIONE_ZONA"]
all_fields=[]
for x in old_fields+default_fields:
    if x and x not in all_fields: all_fields.append(x)
with QUEUE.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=all_fields,extrasaction="ignore"); w.writeheader(); w.writerows(old)

print(json.dumps({"agencies":len(agencies),"agency_candidates":len(rows),"master_after_agencies":len(old)},ensure_ascii=False))
