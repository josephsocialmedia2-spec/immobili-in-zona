#!/usr/bin/env python3
"""Unisce i worker per-annuncio e genera i file operativi finali."""
import csv, json, re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
STATE=DATA/"state.json"
QUEUE=DATA/"work_queue.csv"
INPUT=ROOT/"item_results"
AREA_OUT=DATA/"area_radar.csv"
CONTACT_OUT=DATA/"public_enrichment.csv"
RPO=ROOT/"rpo_approved.csv"

def norm_phone(v):
    d=re.sub(r"\D","",v or "")
    return d[2:] if d.startswith("39") and len(d)>10 else d

def load_rpo():
    ok=set()
    if not RPO.exists(): return ok
    with RPO.open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("approved") or "").strip().upper()!="SI": continue
            p=norm_phone(r.get("telefono") or "")
            if p: ok.add(p)
    return ok

try: state=json.loads(STATE.read_text(encoding="utf-8"))
except Exception: state={"items":{}}
items=state.get("items") or {}; rpo_ok=load_rpo(); merged=0
for path in sorted(INPUT.rglob("*.json")) if INPUT.exists() else []:
    try: doc=json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"SKIP {path}: {e}"); continue
    item_id=(doc.get("item_id") or "").strip(); x=items.get(item_id)
    if not x: continue
    e=doc.get("enrichment") or {}; area=doc.get("area") or {}; actions=[]
    for a in area.get("nearby_public_addresses") or []:
        actions.append({"azione":"VAI_IN_ZONA","target":a,"telefono":"","stato":"PRONTO"})
    for c in e.get("public_contacts") or []:
        if c.get("type")!="PHONE" or c.get("confidence") not in {"HIGH","MEDIUM"}: continue
        approved=norm_phone(c.get("value") or "") in rpo_ok
        actions.append({
            "azione":"CHIAMA" if approved else "VERIFICA_RPO",
            "target":e.get("seller_name") or "inserzionista",
            "telefono":c.get("value", ""),
            "stato":"PRONTO" if approved else "BLOCCATO_FINCHÉ_NON_VERIFICATO",
            "source_url":c.get("source_url","")
        })
    area["actions"]=actions; x["enrichment"]=e; x["area_radar"]=area; merged+=1

state["items"]=items
STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")

area_fields=["ITEM_ID","COMUNE","TIPO_ANNUNCIO","VIA_RADAR","AZIONE","TARGET","TELEFONO","STATO","FONTE"]
area_rows=[]; contact_rows=[]
for item_id,x in items.items():
    e=x.get("enrichment") or {}; area=x.get("area_radar") or {}
    for a in area.get("actions") or []:
        area_rows.append({
            "ITEM_ID":item_id,"COMUNE":x.get("comune",""),"TIPO_ANNUNCIO":x.get("seller_hint","NON_DETERMINATO"),
            "VIA_RADAR":area.get("street",""),"AZIONE":a.get("azione",""),"TARGET":a.get("target",""),
            "TELEFONO":a.get("telefono",""),"STATO":a.get("stato",""),"FONTE":a.get("source_url") or x.get("url","")
        })
    for c in e.get("public_contacts") or []:
        if c.get("confidence") not in {"HIGH","MEDIUM"}: continue
        contact_rows.append({
            "ITEM_ID":item_id,"COMUNE":x.get("comune",""),"TITOLO":x.get("title",""),"TIPO":c.get("type",""),
            "VALORE":c.get("value",""),"CONFIDENZA":c.get("confidence",""),"FONTE_TIPO":c.get("source_type",""),
            "FONTE_URL":c.get("source_url",""),"CROSS_MATCH":e.get("cross_match_count",0),"SELLER_NAME":e.get("seller_name",""),
            "CHECKED_AT":e.get("checked_at","")
        })
with AREA_OUT.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=area_fields); w.writeheader(); w.writerows(area_rows)
contact_fields=["ITEM_ID","COMUNE","TITOLO","TIPO","VALORE","CONFIDENZA","FONTE_TIPO","FONTE_URL","CROSS_MATCH","SELLER_NAME","CHECKED_AT"]
with CONTACT_OUT.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=contact_fields); w.writeheader(); w.writerows(contact_rows)

if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig",newline="") as f:
        qrows=list(csv.DictReader(f)); fields=list(qrows[0].keys()) if qrows else []
    extras=["CONTATTO_PRONTO","CONTATTI_PUBBLICI","FONTE_CONTATTO","CROSS_MATCH","NOME_INSERZIONISTA","RICERCA_PUBBLICA","VIA_RADAR","INDIRIZZI_ZONA","AZIONE_ZONA"]
    fields += [k for k in extras if k not in fields]
    by_url={(x.get("url") or "").strip():x for x in items.values()}
    for r in qrows:
        x=by_url.get((r.get("URL") or "").strip(),{}); e=x.get("enrichment") or {}; area=x.get("area_radar") or {}
        ready=[c for c in (e.get("public_contacts") or []) if c.get("confidence") in {"HIGH","MEDIUM"}]
        r["CONTATTO_PRONTO"]="SI" if ready else "NO"
        r["CONTATTI_PUBBLICI"]=" | ".join(f"{c.get('type')}:{c.get('value')}" for c in ready[:4])
        r["FONTE_CONTATTO"]=" | ".join(dict.fromkeys(c.get("source_url","") for c in ready if c.get("source_url")))
        r["CROSS_MATCH"]=str(e.get("cross_match_count") or 0); r["NOME_INSERZIONISTA"]=e.get("seller_name") or ""
        r["RICERCA_PUBBLICA"]="ESEGUITA" if e else "NON_ESEGUITA"; r["VIA_RADAR"]=area.get("street","")
        r["INDIRIZZI_ZONA"]=" | ".join((area.get("nearby_public_addresses") or [])[:8])
        acts=area.get("actions") or []; labels=[]
        if any(a.get("azione")=="VAI_IN_ZONA" for a in acts): labels.append("VAI IN ZONA")
        if any(a.get("azione")=="CHIAMA" for a in acts): labels.append("CHIAMA")
        if any(a.get("azione")=="VERIFICA_RPO" for a in acts): labels.append("VERIFICA RPO")
        r["AZIONE_ZONA"]=" + ".join(labels)
    with QUEUE.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(qrows)

print(f"MERGE ITEM: {merged} worker uniti, {len(area_rows)} azioni area, {len(contact_rows)} contatti pubblici.")
