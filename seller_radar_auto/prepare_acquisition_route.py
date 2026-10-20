#!/usr/bin/env python3
"""Prepara Giro Acquisizione preservando sempre il master."""
import csv, json, re, unicodedata
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
QUEUE=DATA/"work_queue.csv"
MUNICIPALITIES=(ROOT/"data"/"municipalities_operational.csv") if (ROOT/"data"/"municipalities_operational.csv").exists() else (ROOT/"municipalities.csv")
CONFIG=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
OUT=DATA/"giro_acquisizione.csv"
OUT_TODAY=DATA/"giro_acquisizione_oggi.csv"
OUT_VERIFY=DATA/"giro_da_verificare.csv"
OUT_BACKLOG=DATA/"giro_backlog.csv"
OUT_SUMMARY=DATA/"giro_riepilogo.json"
OUT_STATES={"USCITO_MERCATO","REMOVED","EXPIRED","OUT"}

ADDRESS_RE=re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|localit[aà]|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s,]{2,100}?[,\s]+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|[A-Za-z])?\b", re.I)
STREET_RE=re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|localit[aà]|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s]{2,100}?(?=,|\s+-\s+|$)", re.I)

def norm(v):
    s=unicodedata.normalize("NFKD",str(v or ""))
    s="".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",s)).strip()

def clean(v): return re.sub(r"\s+"," ",str(v or "")).strip(" ,.;")

def load_active():
    with MUNICIPALITIES.open(encoding="utf-8-sig",newline="") as f:
        return {norm(r["comune"]) for r in csv.DictReader(f) if str(r.get("enabled",""))=="1"}

def address(row):
    for text in [row.get("VIA_RADAR",""),row.get("INDIRIZZI_ZONA",""),row.get("TITOLO","")]:
        text=clean(text)
        m=ADDRESS_RE.search(text)
        if m:return clean(m.group(0))
        m=STREET_RE.search(text)
        if m:return clean(m.group(0))
    return "INDIRIZZO DA VERIFICARE"

def score(r):
    try:return int(float(r.get("SCORE") or 0))
    except:return 0

def write(path,fields,rows):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)

active=load_active()
DATA.mkdir(exist_ok=True)
rows=[]
if QUEUE.exists():
    with QUEUE.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))

route=[]
for r in rows:
    comune=r.get("COMUNE","")
    addr=address(r)
    lifecycle=(r.get("STATO") or "").upper()
    in_territory=norm(comune) in active
    if lifecycle in OUT_STATES: state="STORICO_NON_ATTIVO"
    elif not in_territory: state="BACKLOG"
    elif addr=="INDIRIZZO DA VERIFICARE": state="DA_VERIFICARE"
    else: state="FERMATA_PRONTA"
    route.append({
      "TERRITORIO_OPERATIVO":"SI" if in_territory else "NO",
      "STATO_GIRO":state,"STATO_MERCATO":lifecycle,
      "PRIORITA":r.get("PRIORITA",""),"SCORE":r.get("SCORE",""),
      "TIPO_OPPORTUNITA":r.get("TIPO_OPPORTUNITA",""),"TARGET":r.get("TARGET",""),
      "COMUNE":comune,"DOVE_ANDRE":addr,"COSA_CERCO":r.get("TITOLO",""),
      "PREZZO":r.get("PREZZO","") or "PREZZO DA VERIFICARE",
      "FONTE":r.get("FONTE",""),"SELLER_SIGNAL":r.get("INDIZIO_INSERZIONISTA",""),
      "AZIONE":"APRI FONTE E VERIFICA INDIRIZZO" if state=="DA_VERIFICARE" else ("VAI IN ZONA" if state=="FERMATA_PRONTA" else ""),
      "URL":r.get("URL","")
    })

fields=["TERRITORIO_OPERATIVO","STATO_GIRO","STATO_MERCATO","PRIORITA","SCORE","TIPO_OPPORTUNITA",
        "TARGET","COMUNE","DOVE_ANDRE","COSA_CERCO","PREZZO","FONTE","SELLER_SIGNAL","AZIONE","URL"]
route.sort(key=score,reverse=True)
today=[r for r in route if r["TERRITORIO_OPERATIVO"]=="SI" and r["STATO_GIRO"]!="STORICO_NON_ATTIVO"]
verify=[r for r in today if r["STATO_GIRO"]=="DA_VERIFICARE"]
backlog=[r for r in route if r["STATO_GIRO"]=="BACKLOG"]
write(OUT,fields,route);write(OUT_TODAY,fields,today);write(OUT_VERIFY,fields,verify);write(OUT_BACKLOG,fields,backlog)

summary={
 "seller_master_totali":len(route),
 "seller_attivi_master":sum(r["STATO_GIRO"]!="STORICO_NON_ATTIVO" for r in route),
 "storico_non_attivo":sum(r["STATO_GIRO"]=="STORICO_NON_ATTIVO" for r in route),
 "nel_territorio_attivo":len(today),
 "fermate_pronte":sum(r["STATO_GIRO"]=="FERMATA_PRONTA" for r in today),
 "indirizzo_da_verificare":len(verify),
 "backlog_fuori_territorio":len(backlog),
 "territori_operativi_configurati":len(active),
 "centro_operativo":CONFIG["center"]["name"],
 "raggio_operativo":f'{CONFIG["center"]["radius_km"]} km'
}
OUT_SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print("GIRO QA PREP:",summary)
