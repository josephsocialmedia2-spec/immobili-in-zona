#!/usr/bin/env python3
from __future__ import annotations
import csv, datetime as dt, hashlib, json, re, time, unicodedata, urllib.parse
from pathlib import Path
from search_engine import search

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
CONFIG=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
MATRIX=DATA/"discovery_matrix.json"
INCOMING=DATA/"incoming_search_results.csv"
QUEUE=DATA/"work_queue.csv"
TODAY=dt.date.today().isoformat()

def norm_text(v):
    s=unicodedata.normalize("NFKD",str(v or ""))
    s="".join(c for c in s if not unicodedata.combining(c)).casefold()
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",s)).strip()

def norm_url(u):
    try:
        p=urllib.parse.urlsplit((u or "").strip())
        path=re.sub(r"/+$","",p.path)
        return urllib.parse.urlunsplit((p.scheme.lower(),p.netloc.lower(),path,"",""))
    except Exception:
        return (u or "").strip()

def rid(url):
    return "RADAR-"+hashlib.sha1(norm_url(url).encode("utf-8")).hexdigest()[:16].upper()

def extract_price(text):
    t=text or ""
    for pat in [r"€\s*([0-9][0-9. ]{2,})",r"([0-9][0-9. ]{2,})\s*€"]:
        m=re.search(pat,t)
        if m:
            v=re.sub(r"[^0-9]","",m.group(1))
            if v and 1000 <= int(v) <= 50000000: return v
    return ""

ADDRESS_RE=re.compile(r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|localit[aà]|vicolo|largo)\s+[A-Za-zÀ-ÿ0-9'’.\-\s]{2,80}(?:\s+\d{1,4}[A-Za-z]?)?",re.I)
def extract_address(text):
    m=ADDRESS_RE.search(text or "")
    return " ".join(m.group(0).split()) if m else ""

if not MATRIX.exists():
    raise SystemExit("discovery_matrix.json assente: eseguire build_discovery_matrix.py")

targets=json.loads(MATRIX.read_text(encoding="utf-8")).get("targets",[])
cfg=CONFIG.get("discovery",{})
maxq=int(cfg.get("max_queries_per_run",700))
lim=int(cfg.get("max_results_per_query",20))
delay=float(cfg.get("request_delay_seconds",0.35))
modes=cfg.get("query_modes",["AGENCIES","PORTALS","PRIVATE","CLASSIFIED_SOCIAL"])
portal_domains=cfg.get("portal_domains",[])
classified_domains=cfg.get("classified_domains",[])

portal_clause=" OR ".join(f"site:{d}" for d in portal_domains)
classified_clause=" OR ".join(f"site:{d}" for d in classified_domains)

def queries_for(place,comune):
    base=f'"{place}"'
    if norm_text(place)!=norm_text(comune):
        base+=f' "{comune}"'
    out=[]
    for mode in modes:
        if mode=="AGENCIES":
            q=f'{base} vendita immobile "agenzia immobiliare"'
        elif mode=="PORTALS":
            q=f'{base} vendita immobile ({portal_clause})'
        elif mode=="PRIVATE":
            q=f'{base} vendita casa ("privato" OR "da privato" OR "senza agenzia")'
        elif mode=="CLASSIFIED_SOCIAL":
            q=f'{base} vendita casa ({classified_clause})'
        else:
            continue
        out.append((mode,q))
    return out

rows=[]
seen=set()
qcount=0
for t in targets:
    place=(t.get("localita") or t.get("comune") or "").strip()
    comune=(t.get("comune") or "").strip()
    if not place or not comune: continue
    for mode,query in queries_for(place,comune):
        if qcount>=maxq: break
        for x in search(query,limit=lim,delay=delay):
            u=norm_url(x.get("url",""))
            if not u or u in seen: continue
            title=x.get("title","") or ""
            snip=x.get("snippet","") or ""
            blob=" ".join([title,snip,u])
            nb=norm_text(blob)
            # gate geografico: evita risultati omonimi fuori territorio
            place_hit=norm_text(place) in nb
            comune_hit=norm_text(comune) in nb
            if not (place_hit or comune_hit):
                continue
            seen.add(u)
            price=extract_price(blob)
            address=extract_address(blob)
            rows.append({
                "ID":rid(u),"MODE":mode,"COMUNE":comune,"LOCALITA":t.get("localita",""),
                "TITOLO":title,"PREZZO":price,"INDIRIZZO_ESTRATTO":address,
                "URL":u,"SNIPPET":snip,"QUERY":query,
                "GEO_MATCH":"LOCALITA" if place_hit and t.get("localita") else "COMUNE"
            })
        qcount+=1
        time.sleep(delay)
    if qcount>=maxq: break

DATA.mkdir(exist_ok=True)
fields=["ID","MODE","COMUNE","LOCALITA","TITOLO","PREZZO","INDIRIZZO_ESTRATTO","URL","SNIPPET","QUERY","GEO_MATCH"]
with INCOMING.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

old=[]; old_fields=[]
if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f); old=list(reader); old_fields=list(reader.fieldnames or [])
byurl={norm_url(r.get("URL","")):r for r in old if r.get("URL")}

for x in rows:
    key=norm_url(x["URL"])
    if key in byurl:
        r=byurl[key]
        old_price=re.sub(r"[^0-9]","",str(r.get("PREZZO") or ""))
        new_price=re.sub(r"[^0-9]","",str(x.get("PREZZO") or ""))
        if new_price and old_price and new_price != old_price:
            r["PREZZO_PRECEDENTE"]=old_price
            r["PREZZO"]=new_price
            if int(new_price)<int(old_price):
                try:r["RIBASSI"]=str(int(r.get("RIBASSI") or 0)+1)
                except:r["RIBASSI"]="1"
        elif new_price and not old_price:
            r["PREZZO"]=new_price
        r["ULTIMO_CONTROLLO"]=TODAY
        if (r.get("STATO") or "").upper()=="NEW": r["STATO"]="TRACKED"
        if not r.get("VIA_RADAR") and x.get("INDIRIZZO_ESTRATTO"): r["VIA_RADAR"]=x["INDIRIZZO_ESTRATTO"]
        continue

    mode=x["MODE"]
    if mode=="PRIVATE":
        typ,signal,score,priority="FSBO_CANDIDATE","INDIZIO_PRIVATO","55","ALTA"
    elif mode=="CLASSIFIED_SOCIAL":
        typ,signal,score,priority="FSBO_CANDIDATE","INDIZIO_PRIVATO","45","MEDIA"
    elif mode=="AGENCIES":
        typ,signal,score,priority="AGENCY_LISTING","AGENZIA","25","MEDIA"
    else:
        typ,signal,score,priority="MARKET_LISTING","NON_DETERMINATO","20","BASSA"

    rec={
        "PRIORITA":priority,"SCORE":score,"TIPO_OPPORTUNITA":typ,
        "TARGET":"IMMOBILE","FASE_PROGETTO":"","OBIETTIVO_COMMERCIALE":"ACQUISIZIONE IMMOBILE",
        "COMUNE":x["COMUNE"],"FONTE":mode,"TITOLO":x["TITOLO"],
        "PREZZO":x["PREZZO"],"PREZZO_PRECEDENTE":"","RIBASSI":"0",
        "INDIZIO_INSERZIONISTA":signal,"STATO":"NEW",
        "PRIMA_RILEVAZIONE":TODAY,"ULTIMO_CONTROLLO":TODAY,
        "MOTIVI":f'discovery {mode.lower()} geo={x["GEO_MATCH"]}',
        "PDF_DA_VERIFICARE":"","URL":x["URL"],"CONTATTO_PRONTO":"NO",
        "CONTATTI_PUBBLICI":"","FONTE_CONTATTO":"","CROSS_MATCH":"0",
        "NOME_INSERZIONISTA":"","RICERCA_PUBBLICA":x["QUERY"],
        "VIA_RADAR":x["INDIRIZZO_ESTRATTO"],"INDIRIZZI_ZONA":"","AZIONE_ZONA":""
    }
    old.append(rec); byurl[key]=rec

default_fields=[
"PRIORITA","SCORE","TIPO_OPPORTUNITA","TARGET","FASE_PROGETTO","OBIETTIVO_COMMERCIALE",
"COMUNE","FONTE","TITOLO","PREZZO","PREZZO_PRECEDENTE","RIBASSI","INDIZIO_INSERZIONISTA",
"STATO","PRIMA_RILEVAZIONE","ULTIMO_CONTROLLO","MOTIVI","PDF_DA_VERIFICARE","URL",
"CONTATTO_PRONTO","CONTATTI_PUBBLICI","FONTE_CONTATTO","CROSS_MATCH","NOME_INSERZIONISTA",
"RICERCA_PUBBLICA","VIA_RADAR","INDIRIZZI_ZONA","AZIONE_ZONA"
]
all_fields=[]
for col in old_fields+default_fields:
    if col and col not in all_fields: all_fields.append(col)
with QUEUE.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=all_fields,extrasaction="ignore"); w.writeheader(); w.writerows(old)

print(json.dumps({"targets":len(targets),"queries":qcount,"results_geo_valid":len(rows),"master":len(old)},ensure_ascii=False))
