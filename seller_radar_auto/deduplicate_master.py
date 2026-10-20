#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, re, unicodedata
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
QUEUE=DATA/"work_queue.csv"
OUT=DATA/"canonical_properties.csv"
SUMMARY=DATA/"dedupe_summary.json"

def norm(v):
    s=unicodedata.normalize("NFKD",str(v or ""))
    s="".join(c for c in s if not unicodedata.combining(c)).casefold()
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",s)).strip()

def nprice(v):
    s=re.sub(r"[^0-9]","",str(v or ""))
    try:return int(s) if s else None
    except:return None

ADDR=re.compile(r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|localit[aà]|vicolo|largo)\s+[A-Za-zÀ-ÿ0-9'’.\-\s]{2,80}(?:\s+\d{1,4}[A-Za-z]?)?",re.I)
def addr(r):
    for x in [r.get("VIA_RADAR",""),r.get("INDIRIZZI_ZONA",""),r.get("TITOLO","")]:
        m=ADDR.search(x or "")
        if m:return norm(m.group(0))
    return ""

def title_key(v):
    x=norm(v)
    stop={"vendita","immobile","immobili","agenzia","appartamento","casa","villa","in","a","di","con","da","privato"}
    toks=[t for t in x.split() if t not in stop and len(t)>1]
    return " ".join(toks[:16])

if not QUEUE.exists():
    raise SystemExit("work_queue.csv assente")
with QUEUE.open(encoding="utf-8-sig",newline="") as f:
    rows=list(csv.DictReader(f)); fields=list(f.fieldnames or [])

groups=defaultdict(list)
for i,r in enumerate(rows):
    comune=norm(r.get("COMUNE",""))
    a=addr(r); p=nprice(r.get("PREZZO"))
    tk=title_key(r.get("TITOLO",""))
    if a:
        key=("ADDR",comune,a,p or 0)
    elif tk and p:
        key=("TITLE_PRICE",comune,tk,p)
    elif tk:
        key=("TITLE",comune,tk)
    else:
        key=("URL",norm(r.get("URL","")),i)
    groups[key].append((i,r))

out=[]
dup_groups=0
for key,items in groups.items():
    if len(items)>1: dup_groups+=1
    base=max((r for _,r in items),key=lambda r: int(float(r.get("SCORE") or 0)) if str(r.get("SCORE") or "").replace(".","",1).isdigit() else 0)
    urls=[]; sources=[]; agencies=[]
    for _,r in items:
        if r.get("URL") and r["URL"] not in urls: urls.append(r["URL"])
        if r.get("FONTE") and r["FONTE"] not in sources: sources.append(r["FONTE"])
        if r.get("NOME_INSERZIONISTA") and r["NOME_INSERZIONISTA"] not in agencies: agencies.append(r["NOME_INSERZIONISTA"])
    raw="|".join(str(x) for x in key)
    pid="PROP-"+hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14].upper()
    conf="ALTA" if key[0]=="ADDR" and len(items)>1 else ("MEDIA" if len(items)>1 else "UNICA")
    out.append({
      "PROPERTY_ID":pid,
      "COMUNE":base.get("COMUNE",""),
      "INDIRIZZO":base.get("VIA_RADAR","") or base.get("INDIRIZZI_ZONA",""),
      "TITOLO":base.get("TITOLO",""),
      "PREZZO":base.get("PREZZO",""),
      "TIPO_OPPORTUNITA":base.get("TIPO_OPPORTUNITA",""),
      "SELLER_SIGNAL":base.get("INDIZIO_INSERZIONISTA",""),
      "SCORE":base.get("SCORE",""),
      "STATO":base.get("STATO",""),
      "PRIMA_RILEVAZIONE":min([r.get("PRIMA_RILEVAZIONE","") for _,r in items if r.get("PRIMA_RILEVAZIONE")] or [""]),
      "ULTIMO_CONTROLLO":max([r.get("ULTIMO_CONTROLLO","") for _,r in items if r.get("ULTIMO_CONTROLLO")] or [""]),
      "SOURCES_COUNT":len(items),
      "SOURCES":" | ".join(sources),
      "AGENCIES":" | ".join(agencies),
      "URLS":" | ".join(urls),
      "DEDUPE_CONFIDENCE":conf
    })
    for i,r in items:
        r["CROSS_MATCH"]=str(max(0,len(items)-1))

out.sort(key=lambda r:(-(int(float(r["SCORE"])) if str(r["SCORE"]).replace(".","",1).isdigit() else 0),r["COMUNE"]))
ofields=["PROPERTY_ID","COMUNE","INDIRIZZO","TITOLO","PREZZO","TIPO_OPPORTUNITA","SELLER_SIGNAL","SCORE","STATO","PRIMA_RILEVAZIONE","ULTIMO_CONTROLLO","SOURCES_COUNT","SOURCES","AGENCIES","URLS","DEDUPE_CONFIDENCE"]
with OUT.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=ofields);w.writeheader();w.writerows(out)

if "CROSS_MATCH" not in fields: fields.append("CROSS_MATCH")
with QUEUE.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)

summary={"raw_rows":len(rows),"canonical_properties":len(out),"duplicate_groups":dup_groups,"duplicate_excess":len(rows)-len(out),"policy":"RAW MASTER PRESERVED; CANONICAL VIEW ONLY"}
SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False))
