#!/usr/bin/env python3
"""Unisce gli artifact di discovery per comune nello state.json persistente."""
import csv, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"; DATA.mkdir(parents=True,exist_ok=True)
INPUT=ROOT/"discovery_results"
STATE=DATA/"state.json"
STATUS=DATA/"ddg_source_status.csv"

def now(): return datetime.now(timezone.utc).isoformat()
def key(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()[:20]

try: state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"items":{}}
except Exception: state={"items":{}}
items=state.setdefault("items",{})

# Rimuove soltanto i record generati dai prototipi precedenti, non lo storico della pipeline matrix.
for item_id,x in list(items.items()):
    if x.get("discovery_engine") in {"DUCKDUCKGO_HTML","DUCKDUCKGO_HTML_V2","DUCKDUCKGO_AGGREGATED_V3"}:
        del items[item_id]

statuses=[]; current=[]
for path in sorted(INPUT.rglob("*.json")) if INPUT.exists() else []:
    try: doc=json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"SKIP {path}: {e}"); continue
    statuses.extend(doc.get("status") or [])
    current.extend(doc.get("results") or [])

seen_urls=set()
for r in current:
    url=(r.get("url") or "").strip()
    if not url or url in seen_urls: continue
    seen_urls.add(url); i=key(url); p=r.get("price")
    if i not in items:
        items[i]={
            "id":i,"comune":r.get("comune",""),"fonte":r.get("fonte",""),"url":url,
            "title":r.get("title","")[:220],"snippet":"","price_history":[],
            "seller_hint":r.get("seller_hint","NON_DETERMINATO"),"private_intent":bool(r.get("private_intent")),
            "first_seen":now(),"last_seen":now(),"checks":1,"lifecycle":"NEW",
            "domain_rule":r.get("domain_rule",""),"path_rule":r.get("path_rule",""),"discovery_engine":"DDG_MATRIX_V1"
        }
    else:
        x=items[i]; x["last_seen"]=now(); x["checks"]=int(x.get("checks",0))+1
        x["title"]=r.get("title","")[:220] or x.get("title",""); x["fonte"]=r.get("fonte","") or x.get("fonte","")
        x["private_intent"]=bool(x.get("private_intent")) or bool(r.get("private_intent")); x["discovery_engine"]="DDG_MATRIX_V1"
        if r.get("seller_hint") and r.get("seller_hint")!="NON_DETERMINATO": x["seller_hint"]=r["seller_hint"]
        if x.get("lifecycle")=="NEW" and x["checks"]>1: x["lifecycle"]="TRACKED"
    if p:
        hist=items[i].setdefault("price_history",[])
        if not hist or hist[-1].get("price")!=p:
            hist.append({"at":now(),"price":p}); items[i]["price_history"]=hist[-20:]

state["items"]=items; state["matrix_discovery_updated_at"]=now()
STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
fields=["FONTE","COMUNE","STATO","ULTIMO_CONTROLLO","RISULTATI_GREZZI","ACCETTATI","MESSAGGIO","QUERY"]
with STATUS.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(statuses)
print(f"MERGE DISCOVERY: {len(seen_urls)} URL unici, {len(items)} elementi nello storico, {sum(1 for s in statuses if s.get('STATO')=='OK')}/{len(statuses)} query OK.")
