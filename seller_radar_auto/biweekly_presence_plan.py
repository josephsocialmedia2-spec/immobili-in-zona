#!/usr/bin/env python3
import csv, json, os, re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
AREA = DATA / 'area_radar.csv'
EVENTS = DATA / 'intelligence' / 'eventi_mercato.csv'
STATE = DATA / 'presidio_bisettimanale_state.json'
OUT_CSV = DATA / 'presidio_bisettimanale.csv'
OUT_MD = DATA / 'presidio_bisettimanale.md'
OUT_HTML = ROOT / 'presidio_bisettimanale.html'
DUE_FILE = DATA / 'presidio_due.txt'
FORCE = os.getenv('F1_PRESENCE_FORCE','').strip() == '1'
TODAY = datetime.now(timezone.utc)


def load_csv(path):
    if not path.exists(): return []
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def clean(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip(' ,.;')


def key(comune, via):
    return f"{clean(comune).casefold()}|{clean(via).casefold()}"


def parse_dt(s):
    if not s: return None
    try: return datetime.fromisoformat(str(s).replace('Z','+00:00'))
    except Exception: return None


def due(state):
    if FORCE: return True
    last = parse_dt(state.get('last_generated_at'))
    return not last or TODAY - last >= timedelta(days=14)

try:
    pstate = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
except Exception:
    pstate = {}

if not due(pstate):
    DUE_FILE.write_text('NO\n', encoding='utf-8')
    print('PRESIDIO: non ancora dovuto')
    raise SystemExit(0)

area_rows = load_csv(AREA)
event_rows = load_csv(EVENTS)
planned_hist = pstate.get('planned_history') or {}
last_communes = pstate.get('last_communes') or []

# segnali recenti per comune/via
event_by_comune = defaultdict(int)
event_by_key = defaultdict(int)
weights = {'NUOVO_IMMOBILE':8, 'RIBASSO':12, 'USCITO_MERCATO':10, 'VENDUTO_CONFERMATO':14, 'RELISTED':9}
for e in event_rows:
    dt = parse_dt(e.get('data'))
    if dt and TODAY - dt.astimezone(timezone.utc) > timedelta(days=45):
        continue
    c, v, ev = clean(e.get('comune')), clean(e.get('via')), clean(e.get('evento')).upper()
    w = weights.get(ev, 3)
    if c: event_by_comune[c.casefold()] += w
    if c and v: event_by_key[key(c,v)] += w

# raggruppa segnali territoriali per via
by_street = {}
for r in area_rows:
    c = clean(r.get('COMUNE'))
    v = clean(r.get('VIA_RADAR'))
    target = clean(r.get('TARGET'))
    if not c or not v: continue
    k = key(c,v)
    g = by_street.setdefault(k, {'comune':c,'via':v,'targets':[],'direct':0,'agency':0,'unknown':0,'sources':set()})
    if target and target not in g['targets']: g['targets'].append(target)
    typ = clean(r.get('TIPO_OPPORTUNITA')).upper()
    if typ == 'LEAD_DIRETTO': g['direct'] += 1
    elif typ == 'AREA_OPPORTUNITY': g['agency'] += 1
    else: g['unknown'] += 1
    if r.get('FONTE'): g['sources'].add(clean(r.get('FONTE')))

candidates=[]
for k,g in by_street.items():
    score = min(30, len(g['targets'])*4) + g['direct']*10 + g['agency']*4 + g['unknown']*2
    score += event_by_key.get(k,0) + min(25,event_by_comune.get(g['comune'].casefold(),0))
    last = parse_dt(planned_hist.get(k))
    days_since = 999
    if last:
        days_since = max(0,(TODAY-last.astimezone(timezone.utc)).days)
        if days_since < 14: score -= 40
        elif days_since < 28: score -= 15
        elif days_since >= 42: score += 8
    if g['comune'] in last_communes: score -= 8
    candidates.append({**g,'score':score,'days_since':days_since})

# sceglie due comuni compatti: principale + secondario, massimo 10 fermate
comm_scores=defaultdict(int)
for c in candidates: comm_scores[c['comune']] += max(0,c['score'])
selected_communes=[x[0] for x in sorted(comm_scores.items(), key=lambda z:z[1], reverse=True)[:2]]

stops=[]
for comune in selected_communes:
    streets=[x for x in candidates if x['comune']==comune]
    streets.sort(key=lambda x:(x['score'],len(x['targets'])), reverse=True)
    quota=6 if comune==selected_communes[0] else 4
    for s in streets:
        for target in s['targets'][:max(1,quota-len([x for x in stops if x['comune']==comune]))]:
            action='PASSA IN ZONA'
            why=[]
            if s['direct']: why.append(f"{s['direct']} segnale/i privato")
            if s['agency']: why.append(f"{s['agency']} segnale/i agenzia")
            if event_by_key.get(key(s['comune'],s['via'])): why.append('movimenti recenti')
            if not why: why.append('presidio territoriale')
            stops.append({'ordine':len(stops)+1,'comune':s['comune'],'via':s['via'],'target':target,'azione':action,'motivo':', '.join(why),'score':s['score'],'ultima_pianificazione_giorni':s['days_since'] if s['days_since']!=999 else ''})
            if len(stops)>=10: break
        if len(stops)>=10: break
    if len(stops)>=10: break

# fallback: se pochi civici, usa comunque le vie migliori
if len(stops)<8:
    existing={(x['comune'].casefold(),x['via'].casefold()) for x in stops}
    for s in sorted(candidates,key=lambda x:x['score'],reverse=True):
        if len(stops)>=10: break
        kv=(s['comune'].casefold(),s['via'].casefold())
        if kv in existing: continue
        stops.append({'ordine':len(stops)+1,'comune':s['comune'],'via':s['via'],'target':s['via'],'azione':'PRESIDIA LA VIA','motivo':'zona con segnali immobiliari; civico da definire sul posto','score':s['score'],'ultima_pianificazione_giorni':s['days_since'] if s['days_since']!=999 else ''})
        existing.add(kv)

fields=['ordine','comune','via','target','azione','motivo','score','ultima_pianificazione_giorni']
OUT_CSV.parent.mkdir(parents=True,exist_ok=True)
with OUT_CSV.open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(stops)

when=TODAY.astimezone().strftime('%d/%m/%Y')
lines=[f"# GIRO F1 — presidio bisettimanale — {when}","","Obiettivo: presenza ripetuta e sostenibile, con fermate concentrate. Telefoni commerciali solo dopo gate RPO; nessun nominativo di proprietario viene inferito dal vicinato.",""]
for s in stops:
    lines.append(f"{s['ordine']}. **{s['comune']} — {s['target']}** — {s['azione']} — {s['motivo']} — score {s['score']}")
lines += ["","## Regola operativa","- 8–12 fermate, concentrate su massimo 2 Comuni.","- Lascia materiale non nominativo / presentati dove consentito.","- Segna nel CRM se sei passato, così il giro successivo ruota le vie.","- Proprietario: verifica solo tramite fonti ufficiali e legittime; telefono commerciale solo dopo verifica RPO."]
OUT_MD.write_text('\n'.join(lines)+'\n',encoding='utf-8')

rows_html=''.join(f"<tr><td>{s['ordine']}</td><td>{s['comune']}</td><td>{s['target']}</td><td>{s['azione']}</td><td>{s['motivo']}</td><td>{s['score']}</td></tr>" for s in stops)
OUT_HTML.write_text(f'''<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Presidio F1 bisettimanale</title><style>body{{font-family:Arial,sans-serif;background:#f5f4ef;color:#111512;margin:0;padding:24px}}.box{{max-width:1100px;margin:auto;background:#fff;border-radius:18px;padding:22px}}h1{{margin-top:0}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#0e120f;color:white}}.tag{{display:inline-block;background:#39f28a;padding:6px 10px;border-radius:999px;font-weight:700}}@media(max-width:700px){{table,thead,tbody,tr,td{{display:block}}thead{{display:none}}tr{{border:1px solid #ddd;border-radius:12px;margin:10px 0;padding:8px}}td{{border:0}}}}</style><div class="box"><span class="tag">F1 PRESIDIO</span><h1>Giro bisettimanale — {when}</h1><p>Fermate concentrate; priorità a nuovi segnali, ribassi, uscite e vie non presidiate di recente.</p><table><thead><tr><th>#</th><th>Comune</th><th>Dove</th><th>Azione</th><th>Perché</th><th>Score</th></tr></thead><tbody>{rows_html}</tbody></table></div></html>''',encoding='utf-8')

nowiso=TODAY.isoformat()
for s in stops:
    planned_hist[key(s['comune'],s['via'])]=nowiso
pstate['last_generated_at']=nowiso
pstate['last_communes']=selected_communes
pstate['planned_history']=planned_hist
pstate['last_stop_count']=len(stops)
STATE.write_text(json.dumps(pstate,ensure_ascii=False,indent=2),encoding='utf-8')
DUE_FILE.write_text('YES\n',encoding='utf-8')
print(f"PRESIDIO: generato {len(stops)} fermate su {', '.join(selected_communes) or 'nessun comune'}")