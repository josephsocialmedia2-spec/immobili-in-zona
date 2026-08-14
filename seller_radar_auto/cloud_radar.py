#!/usr/bin/env python3
import csv, hashlib, html, json, re, time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"; DATA.mkdir(parents=True,exist_ok=True)
QUERIES=ROOT/"search_queries.csv"
STATE=DATA/"state.json"
QUEUE=DATA/"work_queue.csv"
STATUS=DATA/"source_status.csv"
DASH=ROOT/"dashboard.html"
UA="F1SellerRadar/3.2 (+low-frequency-web-monitor; no-contact-harvesting)"
TIMEOUT=20
TRACK={"gclid","fbclid","msclkid","ref","source"}

def now(): return datetime.now(timezone.utc).isoformat()
def key(s): return hashlib.sha256(s.encode()).hexdigest()[:20]

def norm(url):
    p=urlparse(url)
    q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True)
       if not(k.lower().startswith("utm_") or k.lower() in TRACK)]
    return urlunparse((p.scheme,p.netloc,p.path,p.params,urlencode(q),''))

def clean(s):
    s=re.sub(r"<[^>]+>"," ",s or "")
    return re.sub(r"\s+"," ",html.unescape(s)).strip()

def fetch(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"application/rss+xml,application/xml,text/xml,*/*",
                             "Accept-Language":"it-IT,it;q=0.9"})
    try:
        with urlopen(req,timeout=TIMEOUT) as r:
            body=r.read(800_000).decode(r.headers.get_content_charset() or "utf-8",errors="replace")
            if re.search(r"captcha|verify you are human|access denied",body,re.I):
                return False,0,"","verifica umana / anti-bot"
            return 200<=r.status<400,r.status,body,""
    except HTTPError as e: return False,e.code,"",str(e)
    except (URLError,TimeoutError,OSError) as e: return False,0,"",str(e)

def price(text):
    for pat in [r"€\s*([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})",
                r"([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})\s*€"]:
        m=re.search(pat,text,re.I)
        if m:
            n=int(re.sub(r"\D","",m.group(1)))
            if 5000<=n<=20_000_000:return n
    return None

def seller_hint(text):
    t=clean(text)
    if re.search(r"\b(da privato|annuncio privato|vendita privata|privato vende)\b",t,re.I):
        return "INDIZIO_PRIVATO"
    if re.search(r"\b(agenzia immobiliare|tecnocasa|tecnorete|tempocasa|gabetti|re/?max)\b",t,re.I):
        return "INDIZIO_AGENZIA"
    return "NON_DETERMINATO"

def drops(hist):
    return sum(1 for a,b in zip(hist,hist[1:]) if a.get("price") and b.get("price") and b["price"]<a["price"])

def score(x):
    s=20; why=[]
    if x.get("lifecycle")=="NEW": s+=15; why.append("nuova rilevazione")
    if x.get("intent_query"): s+=10; why.append("query ad intento vendita")
    if x.get("seller_hint")=="INDIZIO_PRIVATO": s+=20; why.append("indizio privato da verificare")
    if x.get("price_history"): s+=5; why.append("prezzo rilevato")
    d=drops(x.get("price_history",[]))
    if d: s+=15; why.append("ribasso rilevato")
    if d>=2: s+=10; why.append("ribassi multipli")
    try:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(x["first_seen"])).days
        if age>=30: s+=10; why.append("30+ giorni monitorati")
        if age>=60: s+=10; why.append("60+ giorni monitorati")
    except Exception: pass
    return min(100,s),why or ["monitoraggio base"]

state={"items":{},"sources":{}}
if STATE.exists():
    try: state.update(json.loads(STATE.read_text(encoding="utf-8")))
    except Exception: pass
items=state.setdefault("items",{})
sources_state={}

with QUERIES.open(encoding="utf-8-sig",newline="") as f:
    queries=[r for r in csv.DictReader(f) if r.get("enabled")=="1" and r.get("query")]

old_sources=state.get("sources",{})
for q in queries:
    qkey="search:"+key(q["query"])
    hours=int(q.get("check_hours") or 6)
    old=old_sources.get(qkey,{})
    if old.get("last_check"):
        try:
            elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(old["last_check"])).total_seconds()/3600
            if elapsed<hours:
                sources_state[qkey]=old
                continue
        except Exception: pass

    rss="https://www.bing.com/search?"+urlencode({"q":q["query"],"format":"rss","count":q.get("max_results") or "15"})
    ok,status,body,error=fetch(rss)
    if not ok:
        sources_state[qkey]={"fonte":"Bing RSS","comune":q["comune"],"label":q["label"],
                             "last_check":now(),"status":"ERROR","message":f"HTTP {status} {error}".strip(),
                             "discovered":0,"seed_url":rss}
        continue
    try:
        root=ET.fromstring(body)
        nodes=root.findall(".//item")
    except ET.ParseError as e:
        sources_state[qkey]={"fonte":"Bing RSS","comune":q["comune"],"label":q["label"],
                             "last_check":now(),"status":"ERROR","message":f"RSS non valido: {e}",
                             "discovered":0,"seed_url":rss}
        continue

    found=0
    for n in nodes[:int(q.get("max_results") or 15)]:
        title=clean(n.findtext("title") or "")
        url=norm((n.findtext("link") or "").strip())
        desc=clean(n.findtext("description") or "")
        if not url.startswith(("http://","https://")) or urlparse(url).netloc.lower().endswith("bing.com"):
            continue
        i=key(url); text=f"{title} {desc}"; p=price(text); hint=seller_hint(text)
        intent=("privato" in q["query"].lower() or "vendo" in q["query"].lower() or "vendesi" in q["query"].lower())
        if i not in items:
            items[i]={"id":i,"comune":q["comune"],"fonte":f"Bing RSS · {q['label']}","url":url,
                      "title":title[:220],"snippet":desc[:500],"price_history":[],"seller_hint":hint,
                      "first_seen":now(),"last_seen":now(),"checks":1,"lifecycle":"NEW","intent_query":intent}
        else:
            x=items[i]; x["last_seen"]=now(); x["checks"]=int(x.get("checks",0))+1
            x["title"]=title[:220] or x.get("title",""); x["snippet"]=desc[:500]
            if hint!="NON_DETERMINATO": x["seller_hint"]=hint
            if x.get("lifecycle")=="NEW" and x["checks"]>1: x["lifecycle"]="TRACKED"
            x["intent_query"]=x.get("intent_query",False) or intent
        if p:
            hist=items[i].setdefault("price_history",[])
            if not hist or hist[-1]["price"]!=p:
                hist.append({"at":now(),"price":p})
                items[i]["price_history"]=hist[-20:]
        found+=1

    sources_state[qkey]={"fonte":"Bing RSS","comune":q["comune"],"label":q["label"],
                         "last_check":now(),"status":"OK","message":"","discovered":found,"seed_url":rss}
    time.sleep(1)

for x in items.values():
    x["score"],x["score_reasons"]=score(x)

STATE.write_text(json.dumps({"updated_at":now(),"items":items,"sources":sources_state},
                            ensure_ascii=False,indent=2),encoding="utf-8")

fields=["PRIORITA","SCORE","COMUNE","FONTE","TITOLO","PREZZO","PREZZO_PRECEDENTE","RIBASSI",
        "INDIZIO_INSERZIONISTA","STATO","PRIMA_RILEVAZIONE","ULTIMO_CONTROLLO","MOTIVI","URL"]
rows=[]
for x in sorted(items.values(),key=lambda z:z.get("score",0),reverse=True):
    hist=x.get("price_history",[])
    rows.append({"PRIORITA":"ALTA" if x["score"]>=75 else "MEDIA" if x["score"]>=50 else "BASSA",
                 "SCORE":x["score"],"COMUNE":x.get("comune",""),"FONTE":x.get("fonte",""),
                 "TITOLO":x.get("title",""),"PREZZO":hist[-1]["price"] if hist else "",
                 "PREZZO_PRECEDENTE":hist[-2]["price"] if len(hist)>1 else "","RIBASSI":drops(hist),
                 "INDIZIO_INSERZIONISTA":x.get("seller_hint","NON_DETERMINATO"),"STATO":x.get("lifecycle",""),
                 "PRIMA_RILEVAZIONE":x.get("first_seen",""),"ULTIMO_CONTROLLO":x.get("last_seen",""),
                 "MOTIVI":" | ".join(x.get("score_reasons",[])),"URL":x.get("url","")})
with QUEUE.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

status_fields=["FONTE","COMUNE","STATO","ULTIMO_CONTROLLO","LINK_SCOPERTI","MESSAGGIO","URL_SORGENTE"]
status_rows=[{"FONTE":s.get("fonte",""),"COMUNE":s.get("comune",""),"STATO":s.get("status",""),
              "ULTIMO_CONTROLLO":s.get("last_check",""),"LINK_SCOPERTI":s.get("discovered",0),
              "MESSAGGIO":s.get("message",""),"URL_SORGENTE":s.get("seed_url","")}
             for s in sources_state.values()]
with STATUS.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=status_fields); w.writeheader(); w.writerows(status_rows)

def euro(v): return "—" if not v else f"€ {int(v):,}".replace(",",".")
high=sum(1 for r in rows if int(r["SCORE"])>=75)
priv=sum(1 for r in rows if r["INDIZIO_INSERZIONISTA"]=="INDIZIO_PRIVATO")
ok=sum(1 for r in status_rows if r["STATO"]=="OK")
trs=[]
for r in rows:
    cls="high" if r["SCORE"]>=75 else "med" if r["SCORE"]>=50 else "low"
    trs.append(f"<tr><td><span class='score {cls}'>{r['SCORE']}</span></td><td>{html.escape(r['PRIORITA'])}</td>"
               f"<td>{html.escape(r['COMUNE'])}</td><td>{html.escape(r['INDIZIO_INSERZIONISTA'])}</td>"
               f"<td>{html.escape(r['TITOLO'])}</td><td>{euro(r['PREZZO'])}</td><td>{r['RIBASSI']}</td>"
               f"<td>{html.escape(r['STATO'])}</td><td>{html.escape(r['MOTIVI'])}</td>"
               f"<td><a href='{html.escape(r['URL'])}' target='_blank'>APRI E VERIFICA</a></td></tr>")
if not trs: trs=["<tr><td colspan='10'>Nessuna opportunità ancora rilevata.</td></tr>"]
DASH.write_text(f"""<!doctype html><html lang='it'><meta charset='utf-8'><title>F1 Seller Radar AUTO</title>
<style>body{{font-family:Segoe UI,Arial;background:#0c0f0d;color:#eee;margin:22px}}.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}}.card{{background:#151a17;border:1px solid #2c3630;padding:14px 18px;border-radius:12px}}table{{width:100%;border-collapse:collapse;background:#141815}}th,td{{padding:9px;border-bottom:1px solid #2c332f;text-align:left;font-size:13px}}th{{background:#1c221e}}a{{color:#78e08f;font-weight:700}}.score{{padding:5px 7px;border-radius:8px;font-weight:800}}.high{{background:#5f2020}}.med{{background:#5d4b17}}.low{{background:#25442f}}.note{{border-left:4px solid #78e08f;padding:12px;background:#171b18}}</style>
<h1>F1 SELLER RADAR — AUTO</h1><div>Aggiornato: {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>
<div class='note'>Ricerca web automatica a bassa frequenza. INDIZIO_PRIVATO va verificato sulla fonte. Nessun telefono, email o nominativo viene raccolto automaticamente.</div>
<div class='cards'><div class='card'>Opportunità: <b>{len(rows)}</b></div><div class='card'>Priorità alta: <b>{high}</b></div><div class='card'>Indizi privato: <b>{priv}</b></div><div class='card'>Canali OK: <b>{ok}/{len(status_rows)}</b></div></div>
<h2>DA LAVORARE</h2><table><tr><th>Score</th><th>Priorità</th><th>Comune</th><th>Inserzionista</th><th>Immobile</th><th>Prezzo</th><th>Ribassi</th><th>Stato</th><th>Perché</th><th>Azione</th></tr>{''.join(trs)}</table>
""",encoding="utf-8")
print(f"F1 Seller Radar AUTO 3.2: {len(rows)} opportunità, {high} priorità alta, {ok} canali OK.")
