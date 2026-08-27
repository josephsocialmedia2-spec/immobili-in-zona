#!/usr/bin/env python3
from __future__ import annotations

import csv, html, json, math, re, statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; INTEL=DATA/'intelligence'; HISTORY=INTEL/'history'
STATE=DATA/'state.json'; QUEUE=DATA/'work_queue.csv'
DASH=ROOT/'intelligence_dashboard.html'; INTEGRATIONS=ROOT/'integrations.json'
ROME=ZoneInfo('Europe/Rome'); NOW=datetime.now(timezone.utc); LOCAL=NOW.astimezone(ROME); TODAY=LOCAL.date().isoformat()
ACTIVE={'NEW','TRACKED','RELISTED'}
TYPE_PATTERNS=[('villa',r'\b(villa|villetta|villino)\b'),('appartamento',r'\b(appartamento|alloggio|quadrilocale|trilocale|bilocale|monolocale)\b'),('casa indipendente',r'\b(casa indipendente|indipendente|terratetto|casa semiindipendente)\b'),('rustico/casale',r'\b(rustico|casale|cascina|baita)\b'),('mansarda',r'\bmansarda\b'),('terreno',r'\bterreno\b'),('commerciale',r'\b(negozio|ufficio|capannone|locale commerciale)\b')]

def dt(v):
    if not v:return None
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except Exception:return None

def n(v):
    if v in (None,''):return None
    if isinstance(v,(int,float)):return float(v)
    s=str(v).strip().replace('€','').replace('EUR','').replace(' ','')
    if ',' in s:s=s.split(',',1)[0]
    if '.' in s and all(len(x)==3 for x in s.split('.')[1:]):s=s.replace('.','')
    try:return float(s)
    except Exception:return None

def mean(v):
    a=[float(x) for x in v if x is not None]
    return round(statistics.mean(a),2) if a else None

def med(v):
    a=[float(x) for x in v if x is not None]
    return round(statistics.median(a),2) if a else None

def load_csv(p):
    if not p.exists():return []
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def write_csv(p,rows,fields):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def sqm(text):
    for pat in [r'\b(?:mq|m²|m2)\s*[:\-]?\s*(\d{2,4}(?:[\.,]\d+)?)\b',r'\b(\d{2,4}(?:[\.,]\d+)?)\s*(?:mq|m²|m2)\b']:
        m=re.search(pat,text or '',re.I)
        if m:
            try:
                x=float(m.group(1).replace(',','.'))
                if 15<=x<=5000:return x
            except Exception:pass
    return None

def typology(text):
    low=(text or '').lower()
    for lab,pat in TYPE_PATTERNS:
        if re.search(pat,low,re.I):return lab
    return 'altro'

def clean_addr(v):return re.sub(r'\s+',' ',(v or '').strip(' ,;-'))[:160]
def street(v):return re.sub(r'\s*,?\s+\d+[A-Za-z]?(?:\s*/\s*[A-Za-z0-9]+)?\s*$','',v or '').strip(' ,-.')
def recent(v,days):
    d=dt(v);return bool(d and d>=NOW-timedelta(days=days))

def sold(x):
    if str(x.get('lifecycle','')).upper() in {'SOLD','VENDUTO','VENDUTO_CONFERMATO'}:return True
    return bool(re.search(r'\b(venduto|immobile venduto|aggiudicato)\b',f"{x.get('title','')} {x.get('snippet','')}".lower()))

def agency(x,q):
    name=((x.get('enrichment') or {}).get('seller_name') or q.get('NOME_INSERZIONISTA') or '').strip()
    return '' if name.upper() in {'','NON_DETERMINATO','PRIVATO','PRIVATO DIRETTO'} else name[:120]

def address(x,q):
    e=x.get('enrichment') or {};a=x.get('area_radar') or {}
    cand=list(e.get('address_hints') or [])+list(a.get('reference_addresses') or [])+[q.get('VIA_RADAR',''),q.get('DOVE_ANDRE','')]
    for c in cand:
        c=clean_addr(c)
        if c and 'VERIFICARE' not in c.upper():return c
    return ''

def prices(x,q):
    hist=[]
    for p in x.get('price_history') or []:
        pv=n(p.get('price'));at=dt(p.get('at'))
        if pv:hist.append((at,pv))
    hist.sort(key=lambda z:z[0] or datetime.min.replace(tzinfo=timezone.utc))
    cur=hist[-1][1] if hist else n(q.get('PREZZO'));prev=hist[-2][1] if len(hist)>1 else n(q.get('PREZZO_PRECEDENTE'))
    cuts=[]
    for (a,p1),(b,p2) in zip(hist,hist[1:]):
        if p2<p1:cuts.append((b,p1,p2,(p1-p2)/p1*100 if p1 else None))
    return hist,cur,prev,cuts

def record(x,q):
    first=dt(x.get('first_seen') or q.get('PRIMA_RILEVAZIONE'));last=dt(x.get('last_seen') or q.get('ULTIMO_CONTROLLO'))
    state=str(x.get('lifecycle') or q.get('STATO') or '').upper();active=state in ACTIVE
    hist,price,prev,cuts=prices(x,q);text=f"{x.get('title','')} {x.get('snippet','')}";m=sqm(text);addr=address(x,q)
    end=NOW if active else (last or NOW);dom=max(0,(end-first).days) if first else None
    first_cut=cuts[0][0] if cuts else None;days_cut=max(0,(first_cut-first).days) if first and first_cut else None
    initial=hist[0][1] if hist else (prev or price);cut_pct=((initial-price)/initial*100) if initial and price and price<initial else 0
    return {'id':x.get('id',''),'comune':x.get('comune') or q.get('COMUNE',''),'via':addr,'strada':street(addr),'tipologia':typology(text),'titolo':x.get('title') or q.get('TITOLO',''),'fonte':x.get('fonte') or q.get('FONTE',''),'agenzia':agency(x,q),'url':x.get('url') or q.get('URL',''),'stato':state,'attivo':active,'venduto_confermato':sold(x),'prima_rilevazione':first.isoformat() if first else '','ultimo_avvistamento':last.isoformat() if last else '','giorni_mercato':dom,'prezzo':round(price,2) if price else None,'prezzo_precedente':round(prev,2) if prev else None,'mq':round(m,2) if m else None,'prezzo_mq':round(price/m,2) if price and m else None,'numero_ribassi':len(cuts),'primo_ribasso':first_cut.isoformat() if first_cut else '','ultimo_ribasso':cuts[-1][0].isoformat() if cuts and cuts[-1][0] else '','giorni_al_primo_ribasso':days_cut,'ribasso_totale_pct':round(cut_pct,2),'cross_match':int((x.get('enrichment') or {}).get('cross_match_count') or q.get('CROSS_MATCH') or 0),'missed_checks':int(x.get('missed_checks') or 0)}

def changes(prev,cur):
    out=[];stamp=LOCAL.isoformat(timespec='seconds')
    for i,c in cur.items():
        o=prev.get(i);base={'data':stamp,'id':i,'comune':c['comune'],'via':c['via'],'agenzia':c['agenzia'],'url':c['url']}
        if not o:
            out.append({**base,'evento':'NUOVO_IMMOBILE','valore_precedente':'','valore_nuovo':c.get('prezzo') or ''});continue
        op,cp=o.get('prezzo'),c.get('prezzo')
        if op and cp and cp<op:out.append({**base,'evento':'RIBASSO','valore_precedente':op,'valore_nuovo':cp,'dettaglio':f"-{round((op-cp)/op*100,2)}%"})
        elif op and cp and cp>op:out.append({**base,'evento':'AUMENTO_PREZZO','valore_precedente':op,'valore_nuovo':cp})
        if o.get('attivo') and not c.get('attivo'):out.append({**base,'evento':'USCITA_OSSERVATA','valore_precedente':o.get('stato',''),'valore_nuovo':c.get('stato',''),'dettaglio':'Non equivale automaticamente a vendita'})
        if not o.get('attivo') and c.get('attivo'):out.append({**base,'evento':'RIENTRO_RIPUBBLICAZIONE','valore_precedente':o.get('stato',''),'valore_nuovo':c.get('stato','')})
        if o.get('agenzia') and c.get('agenzia') and o.get('agenzia')!=c.get('agenzia'):out.append({**base,'evento':'CAMBIO_AGENZIA','valore_precedente':o.get('agenzia'),'valore_nuovo':c.get('agenzia')})
        if not o.get('via') and c.get('via'):out.append({**base,'evento':'INDIRIZZO_TROVATO','valore_precedente':'','valore_nuovo':c.get('via')})
    return out

def groups(rows,keys):
    d=defaultdict(list)
    for r in rows:d[tuple(r.get(k,'') for k in keys)].append(r)
    return d

def kpi_comuni(items):
    rows=[]
    for (c,),rs in sorted(groups(items,['comune']).items()):
        a=[r for r in rs if r['attivo']];cuts=[r for r in rs if r['numero_ribassi']];types=Counter(r['tipologia'] for r in a)
        exited=[r for r in rs if not r['attivo'] and r['giorni_mercato'] is not None];bt=defaultdict(list)
        for r in exited:bt[r['tipologia']].append(r['giorni_mercato'])
        elig=[(t,statistics.median(v),len(v)) for t,v in bt.items() if len(v)>=2] or [(t,statistics.median(v),len(v)) for t,v in bt.items()]
        exits=sum((not r['attivo']) and recent(r['ultimo_avvistamento'],30) for r in rs)
        rows.append({'COMUNE':c,'STOCK_ATTIVO':len(a),'NUOVI_30G':sum(recent(r['prima_rilevazione'],30) for r in rs),'USCITE_OSSERVATE_30G':exits,'RIBASSI_30G':sum(bool(r['ultimo_ribasso']) and recent(r['ultimo_ribasso'],30) for r in rs),'PREZZO_MEDIO':mean([r['prezzo'] for r in a]),'PREZZO_MEDIANO':med([r['prezzo'] for r in a]),'PREZZO_MQ_MEDIO':mean([r['prezzo_mq'] for r in a]),'PREZZO_MQ_MEDIANO':med([r['prezzo_mq'] for r in a]),'PERMANENZA_MEDIANA_GG':med([r['giorni_mercato'] for r in a]),'GIORNI_MEDI_PRIMO_RIBASSO':mean([r['giorni_al_primo_ribasso'] for r in cuts]),'RIBASSO_MEDIO_PCT':mean([r['ribasso_totale_pct'] for r in cuts]),'TURNOVER_OSSERVATO_30G_PCT':round(exits/max(len(a),1)*100,1),'TIPOLOGIA_PIU_OFFERTA':types.most_common(1)[0][0] if types else '','TIPOLOGIA_ROTAZIONE_RAPIDA_PROXY':min(elig,key=lambda z:z[1])[0] if elig else '','VENDUTI_CONFERMATI':sum(bool(r['venduto_confermato']) for r in rs),'ULTIMO_AGGIORNAMENTO':LOCAL.isoformat(timespec='minutes')})
    return rows

def kpi_types(items):
    out=[]
    for (c,t),rs in sorted(groups(items,['comune','tipologia']).items()):
        a=[r for r in rs if r['attivo']]
        out.append({'COMUNE':c,'TIPOLOGIA':t,'STOCK_ATTIVO':len(a),'USCITE_OSSERVATE':sum(not r['attivo'] for r in rs),'PREZZO_MEDIANO':med([r['prezzo'] for r in a]),'PREZZO_MQ_MEDIANO':med([r['prezzo_mq'] for r in a]),'PERMANENZA_MEDIANA_GG':med([r['giorni_mercato'] for r in rs]),'RIBASSO_MEDIO_PCT':mean([r['ribasso_totale_pct'] for r in rs if r['numero_ribassi']])})
    return out

def kpi_streets(items):
    out=[]
    for (c,s),rs in sorted(groups([r for r in items if r['strada']],['comune','strada']).items()):
        a=[r for r in rs if r['attivo']]
        out.append({'COMUNE':c,'VIA':s,'IMMOBILI_MONITORATI':len(rs),'STOCK_ATTIVO':len(a),'PREZZO_MEDIANO':med([r['prezzo'] for r in a]),'PREZZO_MQ_MEDIANO':med([r['prezzo_mq'] for r in a]),'PERMANENZA_MEDIANA_GG':med([r['giorni_mercato'] for r in rs]),'RIBASSI_RILEVATI':sum(r['numero_ribassi'] for r in rs),'USCITE_OSSERVATE':sum(not r['attivo'] for r in rs)})
    return out

def kpi_agencies(items):
    out=[]
    for (ag,),rs in sorted(groups([r for r in items if r['agenzia']],['agenzia']).items()):
        a=[r for r in rs if r['attivo']];ex=sum((not r['attivo']) and recent(r['ultimo_avvistamento'],30) for r in rs);cuts=sum(bool(r['ultimo_ribasso']) and recent(r['ultimo_ribasso'],30) for r in rs);turn=round(ex/max(len(a),1)*100,1)
        out.append({'AGENZIA':ag,'COMUNI':', '.join(sorted({r['comune'] for r in rs if r['comune']})),'STOCK_ATTIVO':len(a),'NUOVI_30G':sum(recent(r['prima_rilevazione'],30) for r in rs),'USCITE_OSSERVATE_30G':ex,'VENDUTI_CONFERMATI':sum(r['venduto_confermato'] for r in rs),'RIBASSI_30G':cuts,'PERMANENZA_MEDIANA_GG':med([r['giorni_mercato'] for r in rs]),'GIORNI_MEDI_PRIMO_RIBASSO':mean([r['giorni_al_primo_ribasso'] for r in rs if r['giorni_al_primo_ribasso'] is not None]),'RIBASSO_MEDIO_PCT':mean([r['ribasso_totale_pct'] for r in rs if r['numero_ribassi']]),'TURNOVER_OSSERVATO_30G_PCT':turn,'SCORE_OPERATIVO':min(100,round(turn*.55+min(ex*6,30)+min(cuts*2,15),1)),'NOTA':'Uscita osservata != vendita certa'})
    return sorted(out,key=lambda r:(r['SCORE_OPERATIVO'],r['USCITE_OSSERVATE_30G']),reverse=True)

def integrations():
    try:return json.loads(INTEGRATIONS.read_text(encoding='utf-8')).get('repos',[])
    except Exception:return []

def dashboard(items,comuni,agencies,types,streets,events):
    payload=json.dumps({'items':items,'comuni':comuni,'agenzie':agencies,'tipologie':types,'vie':streets,'eventi':events[-500:]},ensure_ascii=False).replace('</','<\\/')
    links=''.join(f"<a class='repo' href='{html.escape(r.get('url',''))}' target='_blank'><b>{html.escape(r.get('name',''))}</b><small>{html.escape(r.get('role',''))}</small></a>" for r in integrations())
    return f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>F1 Market Intelligence</title><style>:root{{--g:#39F28A;--bg:#070907;--p:#101510;--line:#29352c;--mut:#aeb7b0;--txt:#fff}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font-family:Arial,sans-serif}}header{{padding:22px;border-bottom:1px solid var(--line);position:sticky;top:0;background:#070907ee;z-index:5}}h1{{margin:0;font-size:24px}}header p{{color:var(--mut);margin:5px 0 0}}main{{max-width:1400px;margin:auto;padding:18px}}.filters{{display:grid;grid-template-columns:1fr 1fr auto;gap:10px;margin-bottom:14px}}input,select,button{{background:#111713;border:1px solid var(--line);color:white;padding:12px;border-radius:10px}}button{{background:var(--g);color:#07100a;font-weight:900}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0 20px}}.card{{background:var(--p);border:1px solid var(--line);border-radius:13px;padding:14px}}.card small{{display:block;color:var(--mut);font-size:10px;text-transform:uppercase}}.card b{{font-size:22px}}section{{margin:22px 0}}h2{{font-size:16px;color:var(--g)}}table{{width:100%;border-collapse:collapse;background:#0e130f}}th,td{{border-bottom:1px solid var(--line);padding:8px;text-align:left;font-size:12px}}th{{color:var(--mut);position:sticky;top:88px;background:#111713}}.scroll{{overflow:auto;max-height:480px;border:1px solid var(--line);border-radius:12px}}.repos{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}}.repo{{text-decoration:none;color:white;background:#111713;border:1px solid var(--line);padding:12px;border-radius:12px}}.repo small{{display:block;color:var(--mut);margin-top:5px}}.warn{{color:#ffda79;font-size:12px}}@media(max-width:700px){{.filters{{grid-template-columns:1fr}}}}</style></head><body><header><h1>F1 MARKET INTELLIGENCE</h1><p>Aggiornato {LOCAL.strftime('%d/%m/%Y %H:%M')} · storico mercato e comportamento agenzie</p></header><main><div class="filters"><select id="comune"><option value="">Tutti i comuni</option></select><input id="via" placeholder="Via / borgata / località"><button onclick="render()">ANALIZZA</button></div><div class="cards" id="cards"></div><p class="warn">Uscita osservata ≠ vendita certa. Le vendite sono conteggiate separatamente solo quando confermate.</p><section><h2>BRIEF VIA / IMMOBILI</h2><div class="scroll"><table><thead><tr><th>Comune</th><th>Via</th><th>Tipo</th><th>Prezzo</th><th>€/m²</th><th>Giorni</th><th>Stato</th><th>Agenzia</th><th>Fonte</th></tr></thead><tbody id="items"></tbody></table></div></section><section><h2>TIPOLOGIE</h2><div class="scroll"><table><thead><tr><th>Tipo</th><th>Stock</th><th>Uscite</th><th>Prezzo mediano</th><th>€/m² mediano</th><th>Permanenza</th><th>Ribasso medio</th></tr></thead><tbody id="types"></tbody></table></div></section><section><h2>CLASSIFICA AGENZIE — PERFORMANCE OSSERVATA</h2><div class="scroll"><table><thead><tr><th>Agenzia</th><th>Stock</th><th>Nuovi 30g</th><th>Uscite 30g</th><th>Ribassi 30g</th><th>Giorni mercato</th><th>Giorni al ribasso</th><th>Ribasso %</th><th>Score</th></tr></thead><tbody id="agencies"></tbody></table></div></section><section><h2>ULTIMI MOVIMENTI</h2><div class="scroll"><table><thead><tr><th>Data</th><th>Comune</th><th>Via</th><th>Evento</th><th>Prima</th><th>Dopo</th><th>Agenzia</th></tr></thead><tbody id="events"></tbody></table></div></section><section><h2>HUB COLLEGATI</h2><div class="repos">{links}</div></section></main><script>const D={payload};const f=n=>n==null||n===''?'—':Number(n).toLocaleString('it-IT',{{maximumFractionDigits:1}});const euro=n=>n==null||n===''?'—':'€ '+Number(n).toLocaleString('it-IT',{{maximumFractionDigits:0}});const sel=document.getElementById('comune');[...new Set(D.items.map(x=>x.comune).filter(Boolean))].sort().forEach(c=>{{let o=document.createElement('option');o.value=c;o.textContent=c;sel.appendChild(o)}});const esc=s=>String(s??'').replace(/[&<>\"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[m]));function render(){{const c=sel.value.toLowerCase(),v=document.getElementById('via').value.trim().toLowerCase();const items=D.items.filter(x=>(!c||x.comune.toLowerCase()===c)&&(!v||(x.via||'').toLowerCase().includes(v)));const active=items.filter(x=>x.attivo),prices=active.map(x=>x.prezzo).filter(Boolean),psm=active.map(x=>x.prezzo_mq).filter(Boolean),dom=items.map(x=>x.giorni_mercato).filter(x=>x!=null);const md=a=>{{if(!a.length)return null;const b=[...a].sort((x,y)=>x-y),m=Math.floor(b.length/2);return b.length%2?b[m]:(b[m-1]+b[m])/2}};document.getElementById('cards').innerHTML=`<div class='card'><small>Monitorati</small><b>${{items.length}}</b></div><div class='card'><small>Stock attivo</small><b>${{active.length}}</b></div><div class='card'><small>Prezzo mediano</small><b>${{euro(md(prices))}}</b></div><div class='card'><small>€/m² mediano</small><b>${{euro(md(psm))}}</b></div><div class='card'><small>Permanenza mediana</small><b>${{f(md(dom))}} gg</b></div><div class='card'><small>Ribassi</small><b>${{items.reduce((s,x)=>s+(x.numero_ribassi||0),0)}}</b></div>`;document.getElementById('items').innerHTML=items.map(x=>`<tr><td>${{esc(x.comune)}}</td><td><a href='${{esc(x.url)}}' target='_blank' style='color:#39F28A'>${{esc(x.via||'DA VERIFICARE')}}</a></td><td>${{esc(x.tipologia)}}</td><td>${{euro(x.prezzo)}}</td><td>${{euro(x.prezzo_mq)}}</td><td>${{f(x.giorni_mercato)}}</td><td>${{esc(x.stato)}}</td><td>${{esc(x.agenzia||'—')}}</td><td>${{esc(x.fonte)}}</td></tr>`).join('')||'<tr><td colspan=9>Nessun dato</td></tr>';document.getElementById('types').innerHTML=D.tipologie.filter(x=>!c||x.COMUNE.toLowerCase()===c).map(x=>`<tr><td>${{esc(x.TIPOLOGIA)}}</td><td>${{f(x.STOCK_ATTIVO)}}</td><td>${{f(x.USCITE_OSSERVATE)}}</td><td>${{euro(x.PREZZO_MEDIANO)}}</td><td>${{euro(x.PREZZO_MQ_MEDIANO)}}</td><td>${{f(x.PERMANENZA_MEDIANA_GG)}} gg</td><td>${{f(x.RIBASSO_MEDIO_PCT)}}%</td></tr>`).join('');document.getElementById('agencies').innerHTML=D.agenzie.filter(x=>!c||(x.COMUNI||'').toLowerCase().includes(c)).slice(0,80).map(x=>`<tr><td>${{esc(x.AGENZIA)}}</td><td>${{f(x.STOCK_ATTIVO)}}</td><td>${{f(x.NUOVI_30G)}}</td><td>${{f(x.USCITE_OSSERVATE_30G)}}</td><td>${{f(x.RIBASSI_30G)}}</td><td>${{f(x.PERMANENZA_MEDIANA_GG)}}</td><td>${{f(x.GIORNI_MEDI_PRIMO_RIBASSO)}}</td><td>${{f(x.RIBASSO_MEDIO_PCT)}}%</td><td>${{f(x.SCORE_OPERATIVO)}}</td></tr>`).join('')||'<tr><td colspan=9>Agenzia non identificata nei dati disponibili</td></tr>';document.getElementById('events').innerHTML=D.eventi.filter(x=>!c||x.comune.toLowerCase()===c).slice().reverse().slice(0,150).map(x=>`<tr><td>${{esc((x.data||'').slice(0,16).replace('T',' '))}}</td><td>${{esc(x.comune)}}</td><td>${{esc(x.via||'—')}}</td><td>${{esc(x.evento)}}</td><td>${{esc(x.valore_precedente??'—')}}</td><td>${{esc(x.valore_nuovo??'—')}}</td><td>${{esc(x.agenzia||'—')}}</td></tr>`).join('')||'<tr><td colspan=7>Nessun movimento registrato</td></tr>';}}sel.addEventListener('change',render);document.getElementById('via').addEventListener('input',render);render();</script></body></html>'''

def main():
    INTEL.mkdir(parents=True,exist_ok=True);HISTORY.mkdir(parents=True,exist_ok=True)
    try:state=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {'items':{}}
    except Exception:state={'items':{}}
    q={r.get('URL',''):r for r in load_csv(QUEUE) if r.get('URL')};items=[record(x,q.get(x.get('url',''),{})) for x in (state.get('items') or {}).values()];items.sort(key=lambda r:(r['comune'],r['strada'],r['tipologia'],r['id']));cur={r['id']:r for r in items if r['id']}
    latest=INTEL/'latest_snapshot.json'
    try:old_list=json.loads(latest.read_text(encoding='utf-8')) if latest.exists() else []
    except Exception:old_list=[]
    prev={r.get('id',''):r for r in old_list if r.get('id')};new_events=changes(prev,cur) if prev else []
    event_path=INTEL/'eventi_mercato.csv';events=load_csv(event_path);seen={(e.get('id'),e.get('evento'),(e.get('data') or '')[:10],str(e.get('valore_nuovo',''))) for e in events}
    for e in new_events:
        k=(e.get('id'),e.get('evento'),(e.get('data') or '')[:10],str(e.get('valore_nuovo','')))
        if k not in seen:events.append(e);seen.add(k)
    ef=['data','id','comune','via','evento','valore_precedente','valore_nuovo','dettaglio','agenzia','url'];write_csv(event_path,events,ef)
    kc=kpi_comuni(items);kt=kpi_types(items);kv=kpi_streets(items);ka=kpi_agencies(items)
    write_csv(INTEL/'kpi_comuni.csv',kc,list(kc[0]) if kc else ['COMUNE']);write_csv(INTEL/'kpi_tipologie.csv',kt,list(kt[0]) if kt else ['COMUNE','TIPOLOGIA']);write_csv(INTEL/'kpi_vie.csv',kv,list(kv[0]) if kv else ['COMUNE','VIA']);write_csv(INTEL/'kpi_agenzie.csv',ka,list(ka[0]) if ka else ['AGENZIA'])
    sf=['id','comune','via','strada','tipologia','titolo','fonte','agenzia','url','stato','attivo','venduto_confermato','prima_rilevazione','ultimo_avvistamento','giorni_mercato','prezzo','prezzo_precedente','mq','prezzo_mq','numero_ribassi','primo_ribasso','ultimo_ribasso','giorni_al_primo_ribasso','ribasso_totale_pct','cross_match','missed_checks'];write_csv(INTEL/'immobili_snapshot.csv',items,sf)
    latest.write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8');(HISTORY/f'{TODAY}.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8');DASH.write_text(dashboard(items,kc,ka,kt,kv,events),encoding='utf-8')
    print(f'Market intelligence: {len(items)} immobili, {len(kc)} comuni, {len(ka)} agenzie, {len(new_events)} nuovi eventi.')

if __name__=='__main__':main()
