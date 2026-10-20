#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, re, time, urllib.parse
from pathlib import Path
from search_engine import search

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
CONFIG=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
MATRIX=DATA/"discovery_matrix.json"
INCOMING=DATA/"incoming_search_results.csv"
QUEUE=DATA/"work_queue.csv"

def norm_url(u):
    try:
        p=urllib.parse.urlsplit(u.strip())
        path=re.sub(r"/+$","",p.path)
        return urllib.parse.urlunsplit((p.scheme.lower(),p.netloc.lower(),path,"",""))
    except Exception:
        return (u or "").strip()

def rid(url):
    return "RADAR-"+hashlib.sha1(norm_url(url).encode("utf-8")).hexdigest()[:16].upper()

if not MATRIX.exists():
    raise SystemExit("discovery_matrix.json assente: eseguire build_discovery_matrix.py")

targets=json.loads(MATRIX.read_text(encoding="utf-8")).get("targets",[])
sources=CONFIG.get("discovery",{}).get("sources",[])
maxq=int(CONFIG.get("discovery",{}).get("max_queries_per_run",80))
lim=int(CONFIG.get("discovery",{}).get("max_results_per_query",20))
delay=float(CONFIG.get("discovery",{}).get("request_delay_seconds",1.5))

rows=[]
seen=set()
qcount=0
for t in targets:
    place=t.get("localita") or t.get("comune")
    comune=t.get("comune") or ""
    for src in sources:
        if qcount>=maxq: break
        query=f'"{place}" "{comune}" {src} vendita immobile'
        for x in search(query, limit=lim, delay=delay):
            u=norm_url(x.get("url",""))
            if not u or u in seen: continue
            seen.add(u)
            rows.append({
                "ID":rid(u),"COMUNE":comune,"LOCALITA":t.get("localita",""),
                "TITOLO":x.get("title",""),"URL":u,"SNIPPET":x.get("snippet",""),
                "QUERY":query,"FONTE_RICERCA":src
            })
        qcount+=1
        time.sleep(delay)
    if qcount>=maxq: break

DATA.mkdir(exist_ok=True)
fields=["ID","COMUNE","LOCALITA","TITOLO","URL","SNIPPET","QUERY","FONTE_RICERCA"]
with INCOMING.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

old=[]
old_fields=[]
if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig",newline="") as f:
        old=list(csv.DictReader(f)); old_fields=list(f.fieldnames or [])
existing={norm_url(r.get("URL","")) for r in old if r.get("URL")}
for x in rows:
    if norm_url(x["URL"]) in existing: continue
    old.append({
        "PRIORITA":"BASSA","SCORE":"10","TIPO_OPPORTUNITA":"DA_ANALIZZARE",
        "TARGET":"IMMOBILE","FASE_PROGETTO":"","OBIETTIVO_COMMERCIALE":"ACQUISIZIONE IMMOBILE",
        "COMUNE":x["COMUNE"],"FONTE":x["FONTE_RICERCA"],"TITOLO":x["TITOLO"],
        "PREZZO":"","PREZZO_PRECEDENTE":"","RIBASSI":"0",
        "INDIZIO_INSERZIONISTA":"NON_DETERMINATO","STATO":"NEW",
        "PRIMA_RILEVAZIONE":"","ULTIMO_CONTROLLO":"","MOTIVI":"discovery web",
        "PDF_DA_VERIFICARE":"","URL":x["URL"],"CONTATTO_PRONTO":"NO",
        "CONTATTI_PUBBLICI":"","FONTE_CONTATTO":"","CROSS_MATCH":"0",
        "NOME_INSERZIONISTA":"","RICERCA_PUBBLICA":x["QUERY"],
        "VIA_RADAR":"","INDIRIZZI_ZONA":"","AZIONE_ZONA":"",
    })
    existing.add(norm_url(x["URL"]))

default_fields=[
"PRIORITA","SCORE","TIPO_OPPORTUNITA","TARGET","FASE_PROGETTO","OBIETTIVO_COMMERCIALE",
"COMUNE","FONTE","TITOLO","PREZZO","PREZZO_PRECEDENTE","RIBASSI","INDIZIO_INSERZIONISTA",
"STATO","PRIMA_RILEVAZIONE","ULTIMO_CONTROLLO","MOTIVI","PDF_DA_VERIFICARE","URL",
"CONTATTO_PRONTO","CONTATTI_PUBBLICI","FONTE_CONTATTO","CROSS_MATCH","NOME_INSERZIONISTA",
"RICERCA_PUBBLICA","VIA_RADAR","INDIRIZZI_ZONA","AZIONE_ZONA"
]
all_fields=[]
for f in old_fields+default_fields:
    if f and f not in all_fields: all_fields.append(f)
with QUEUE.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=all_fields,extrasaction="ignore"); w.writeheader(); w.writerows(old)

print(f"DISCOVERY: query={qcount}; risultati_unici={len(rows)}; master={len(old)}")
