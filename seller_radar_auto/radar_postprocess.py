#!/usr/bin/env python3
import csv, html, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
STATE=DATA/"state.json"
QUEUE=DATA/"work_queue.csv"
DDG_STATUS=DATA/"ddg_source_status.csv"
STATUS=DATA/"source_status.csv"
DASH=ROOT/"dashboard.html"
MUNICIPALITIES=ROOT/"municipalities.csv"
PORTALS=ROOT/"portal_catalog.csv"

def drops(hist):
    return sum(1 for a,b in zip(hist,hist[1:]) if a.get("price") and b.get("price") and b["price"]<a["price"])

def score(x):
    s,why=15,[]
    if x.get("lifecycle")=="NEW": s+=15; why.append("nuova rilevazione")
    if x.get("private_intent"): s+=12; why.append("fonte/query orientata ai privati")
    if x.get("seller_hint")=="INDIZIO_PRIVATO": s+=28; why.append("indizio privato/no agenzie")
    if x.get("seller_hint")=="INDIZIO_AGENZIA": s-=12; why.append("indizio agenzia")
    if x.get("price_history"): s+=5; why.append("prezzo rilevato")
    d=drops(x.get("price_history",[]))
    if d: s+=18; why.append("ribasso rilevato")
    if d>=2: s+=10; why.append("ribassi multipli")
    try:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(x["first_seen"])).days
        if age>=30: s+=8; why.append("30+ giorni monitorati")
        if age>=60: s+=8; why.append("60+ giorni monitorati")
    except Exception: pass
    return max(0,min(100,s)), why or ["monitoraggio base"]

def load_csv(path):
    if not path.exists(): return []
    with path.open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))

try: state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"items":{}}
except Exception: state={"items":{}}
items=state.get("items") or {}
for x in items.values(): x["score"],x["score_reasons"]=score(x)
state["updated_at"]=datetime.now(timezone.utc).isoformat(); state["items"]=items
STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")

fields=["PRIORITA","SCORE","COMUNE","FONTE","TITOLO","PREZZO","PREZZO_PRECEDENTE","RIBASSI","INDIZIO_INSERZIONISTA","STATO","PRIMA_RILEVAZIONE","ULTIMO_CONTROLLO","MOTIVI","URL"]
queue=[]
for x in sorted(items.values(),key=lambda z:z.get("score",0),reverse=True):
    hist=x.get("price_history",[])
    queue.append({
        "PRIORITA":"ALTA" if x["score"]>=70 else "MEDIA" if x["score"]>=45 else "BASSA",
        "SCORE":x["score"],"COMUNE":x.get("comune",""),"FONTE":x.get("fonte",""),"TITOLO":x.get("title",""),
        "PREZZO":hist[-1]["price"] if hist else "","PREZZO_PRECEDENTE":hist[-2]["price"] if len(hist)>1 else "",
        "RIBASSI":drops(hist),"INDIZIO_INSERZIONISTA":x.get("seller_hint","NON_DETERMINATO"),"STATO":x.get("lifecycle",""),
        "PRIMA_RILEVAZIONE":x.get("first_seen",""),"ULTIMO_CONTROLLO":x.get("last_seen",""),"MOTIVI":" | ".join(x.get("score_reasons",[])),"URL":x.get("url","")
    })
with QUEUE.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(queue)

status_rows=load_csv(DDG_STATUS)
status_fields=["FONTE","COMUNE","STATO","ULTIMO_CONTROLLO","RISULTATI_GREZZI","ACCETTATI","MESSAGGIO","URL_SORGENTE"]
with STATUS.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=status_fields); w.writeheader()
    for r in status_rows:
        w.writerow({"FONTE":r.get("FONTE",""),"COMUNE":r.get("COMUNE",""),"STATO":r.get("STATO",""),"ULTIMO_CONTROLLO":r.get("ULTIMO_CONTROLLO",""),"RISULTATI_GREZZI":r.get("RISULTATI_GREZZI","0"),"ACCETTATI":r.get("ACCETTATI","0"),"MESSAGGIO":r.get("MESSAGGIO",""),"URL_SORGENTE":r.get("QUERY","")})

municipalities=[r.get("comune","") for r in load_csv(MUNICIPALITIES) if r.get("enabled")=="1"]
portals=[r for r in load_csv(PORTALS) if r.get("enabled")=="1"]
high=sum(1 for r in queue if int(r["SCORE"])>=70); priv=sum(1 for r in queue if r["INDIZIO_INSERZIONISTA"]=="INDIZIO_PRIVATO")
accepted=sum(int(r.get("ACCETTATI") or 0) for r in status_rows); ok=sum(1 for r in status_rows if r.get("STATO")=="OK")
trs=[]
for r in queue[:1000]:
    cls="high" if int(r["SCORE"])>=70 else "med" if int(r["SCORE"])>=45 else "low"
    trs.append(f"<tr data-comune='{html.escape(r['COMUNE'])}' data-fonte='{html.escape(r['FONTE'])}'><td><span class='score {cls}'>{r['SCORE']}</span></td><td>{html.escape(r['PRIORITA'])}</td><td>{html.escape(r['COMUNE'])}</td><td>{html.escape(r['FONTE'])}</td><td>{html.escape(r['INDIZIO_INSERZIONISTA'])}</td><td>{html.escape(r['TITOLO'])}</td><td>{html.escape(str(r['PREZZO'] or '—'))}</td><td>{r['RIBASSI']}</td><td>{html.escape(r['MOTIVI'])}</td><td><a href='{html.escape(r['URL'])}' target='_blank'>APRI</a></td></tr>")
if not trs: trs=["<tr><td colspan='10'>Nessuna opportunità rilevata.</td></tr>"]
DASH.write_text(f"""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>F1 Seller Radar</title><style>body{{font-family:Segoe UI,Arial;background:#0c0f0d;color:#eee;padding:22px}}.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}}.card{{background:#151a17;border:1px solid #2c3630;padding:14px;border-radius:12px}}table{{width:100%;border-collapse:collapse;background:#141815}}th,td{{padding:8px;border-bottom:1px solid #2c332f;text-align:left;font-size:13px}}a{{color:#78e08f}}.score{{padding:4px 6px;border-radius:7px}}.high{{background:#5f2020}}.med{{background:#5d4b17}}.low{{background:#25442f}}</style></head><body><h1>F1 SELLER RADAR</h1><div>Motore discovery: DuckDuckGo HTML v2 · Aggiornato {datetime.now().strftime('%d/%m/%Y %H:%M')}</div><div class='cards'><div class='card'>Opportunità <b>{len(queue)}</b></div><div class='card'>Priorità alta <b>{high}</b></div><div class='card'>Indizi privato <b>{priv}</b></div><div class='card'>Accettati ciclo <b>{accepted}</b></div><div class='card'>Query OK <b>{ok}/{len(status_rows)}</b></div><div class='card'>Territori <b>{len(municipalities)}</b></div><div class='card'>Portali configurati <b>{len(portals)}</b></div></div><table><thead><tr><th>Score</th><th>Priorità</th><th>Comune</th><th>Fonte</th><th>Inserzionista</th><th>Immobile</th><th>Prezzo</th><th>Ribassi</th><th>Motivi</th><th>Azione</th></tr></thead><tbody>{''.join(trs)}</tbody></table></body></html>""",encoding="utf-8")
print(f"F1 Radar postprocess: {len(queue)} opportunità, {accepted} accettati discovery, {ok}/{len(status_rows)} query OK.")
