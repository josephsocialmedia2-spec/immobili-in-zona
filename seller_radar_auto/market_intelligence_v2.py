#!/usr/bin/env python3
"""F1 Market Intelligence v2: KPI solo su schede immobile di qualità.

Lo storico Radar può contenere vecchie pagine categoria/ricerca. Queste restano
nello state per audit ma non entrano nei KPI di mercato finché non esiste evidenza
che il record rappresenti un singolo immobile.
"""
import json, re
from urllib.parse import urlparse
import market_intelligence as mi

CATEGORY_PATTERNS=[
    r'^case in vendita\b', r'^immobili in vendita\b', r'^vendita case\b',
    r'^case in vendita da privati\b', r'^annunci immobiliari\b',
    r'\bvendita case .+ - subito\.it$', r'\bimmobili - subito\.it$',
    r'\bcase da privati\b', r'\bcase in vendita .+ - idealista$',
]
ADDRESS_RE=re.compile(r'\b(via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo|localit[aà])\b(?:[^|,;]{1,80})',re.I)
DETAIL_URLS=[
    r'/annunci/[0-9]+/?$', r'/immobile/[0-9]+/?$', r'/immobili/[0-9]+/?$',
    r'/it/vendita/.*/[0-9]+/?$', r'-[0-9]{6,}\.htm$', r'/annunci/.+-[0-9]{5,}/?$',
    r'/asta/.+[0-9]{4,}', r'/aste/.+[0-9]{4,}', r'/lotto/[0-9]+',
]

def quality(x,q):
    title=(x.get('title') or q.get('TITOLO') or '').strip()
    low=title.casefold(); url=(x.get('url') or q.get('URL') or '').strip(); path=urlparse(url).path
    addr=mi.address(x,q)
    if addr:
        return True,'INDIRIZZO_ESTRATTO'
    rule=(x.get('path_rule') or '').strip()
    if rule and rule not in {'^/.*$',''}:
        try:
            if re.search(rule,path,re.I): return True,'URL_DETTAGLIO_PORTALE'
        except re.error: pass
    if any(re.search(p,path,re.I) for p in DETAIL_URLS):
        return True,'URL_DETTAGLIO'
    if any(re.search(p,low,re.I) for p in CATEGORY_PATTERNS):
        return False,'PAGINA_CATEGORIA'
    if ADDRESS_RE.search(title):
        return True,'INDIRIZZO_NEL_TITOLO'
    hist,price,_,_=mi.prices(x,q)
    strong_type=bool(re.search(r'\b(villa|appartamento|bilocale|trilocale|quadrilocale|rustico|casale|cascina|mansarda|attico|terratetto|casa indipendente)\b',low,re.I))
    has_size=bool(re.search(r'\b\d{2,4}\s*(?:mq|m²|m2)\b',low,re.I))
    if strong_type and price and has_size:
        return True,'TIPO_PREZZO_METRATURA'
    return False,'EVIDENZA_INSUFFICIENTE'

def main():
    mi.INTEL.mkdir(parents=True,exist_ok=True);mi.HISTORY.mkdir(parents=True,exist_ok=True)
    try:state=json.loads(mi.STATE.read_text(encoding='utf-8')) if mi.STATE.exists() else {'items':{}}
    except Exception:state={'items':{}}
    q={r.get('URL',''):r for r in mi.load_csv(mi.QUEUE) if r.get('URL')}
    kept=[];discard=[]
    for x in (state.get('items') or {}).values():
        qq=q.get(x.get('url',''),{});ok,reason=quality(x,qq)
        if ok:
            r=mi.record(x,qq);r['qualita_record']=reason;r['segnale_mercato']=x.get('market_signal','VENDITA');kept.append(r)
        else:
            discard.append({'ID':x.get('id',''),'COMUNE':x.get('comune',''),'TITOLO':x.get('title',''),'FONTE':x.get('fonte',''),'URL':x.get('url',''),'MOTIVO_SCARTO':reason})
    kept.sort(key=lambda r:(r['comune'],r['strada'],r['tipologia'],r['id']));cur={r['id']:r for r in kept if r['id']}
    latest=mi.INTEL/'latest_snapshot.json'
    try:old_list=json.loads(latest.read_text(encoding='utf-8')) if latest.exists() else []
    except Exception:old_list=[]
    prev={r.get('id',''):r for r in old_list if r.get('id')};new_events=mi.changes(prev,cur) if prev else []
    event_path=mi.INTEL/'eventi_mercato.csv';events=mi.load_csv(event_path);seen={(e.get('id'),e.get('evento'),(e.get('data') or '')[:10],str(e.get('valore_nuovo',''))) for e in events}
    for e in new_events:
        k=(e.get('id'),e.get('evento'),(e.get('data') or '')[:10],str(e.get('valore_nuovo','')))
        if k not in seen:events.append(e);seen.add(k)
    ef=['data','id','comune','via','evento','valore_precedente','valore_nuovo','dettaglio','agenzia','url'];mi.write_csv(event_path,events,ef)
    kc=mi.kpi_comuni(kept);kt=mi.kpi_types(kept);kv=mi.kpi_streets(kept);ka=mi.kpi_agencies(kept)
    # KPI aggiuntivi per segnali di mercato (aste, privati, agenzie, storico/uscite).
    by_comune={}
    for r in kept:
        c=r['comune'];z=by_comune.setdefault(c,{'COMUNE':c,'IMMOBILI_QUALIFICATI':0,'ASTE':0,'PRIVATI':0,'AGENZIE':0,'RIBASSI_SEGNALATI':0,'STORICO_USCITE':0})
        z['IMMOBILI_QUALIFICATI']+=1;sig=(r.get('segnale_mercato') or '').upper()
        z['ASTE']+=int('ASTA' in sig);z['PRIVATI']+=int('PRIVATO' in sig);z['AGENZIE']+=int('AGENZIA' in sig);z['RIBASSI_SEGNALATI']+=int('RIBASSO' in sig);z['STORICO_USCITE']+=int('STORICO_USCITA' in sig)
    ks=list(sorted(by_comune.values(),key=lambda z:z['COMUNE']))
    mi.write_csv(mi.INTEL/'kpi_comuni.csv',kc,list(kc[0]) if kc else ['COMUNE']);mi.write_csv(mi.INTEL/'kpi_tipologie.csv',kt,list(kt[0]) if kt else ['COMUNE','TIPOLOGIA']);mi.write_csv(mi.INTEL/'kpi_vie.csv',kv,list(kv[0]) if kv else ['COMUNE','VIA']);mi.write_csv(mi.INTEL/'kpi_agenzie.csv',ka,list(ka[0]) if ka else ['AGENZIA']);mi.write_csv(mi.INTEL/'kpi_segnali.csv',ks,list(ks[0]) if ks else ['COMUNE']);mi.write_csv(mi.INTEL/'scarti_qualita.csv',discard,['ID','COMUNE','TITOLO','FONTE','URL','MOTIVO_SCARTO'])
    sf=['id','comune','via','strada','tipologia','titolo','fonte','agenzia','url','stato','attivo','venduto_confermato','prima_rilevazione','ultimo_avvistamento','giorni_mercato','prezzo','prezzo_precedente','mq','prezzo_mq','numero_ribassi','primo_ribasso','ultimo_ribasso','giorni_al_primo_ribasso','ribasso_totale_pct','cross_match','missed_checks','qualita_record','segnale_mercato'];mi.write_csv(mi.INTEL/'immobili_snapshot.csv',kept,sf)
    latest.write_text(json.dumps(kept,ensure_ascii=False,indent=2),encoding='utf-8');(mi.HISTORY/f'{mi.TODAY}.json').write_text(json.dumps(kept,ensure_ascii=False,indent=2),encoding='utf-8');mi.DASH.write_text(mi.dashboard(kept,kc,ka,kt,kv,events),encoding='utf-8')
    print(f'Market Intelligence v2: {len(kept)} schede immobile qualificate, {len(discard)} pagine categoria/scarti, {len(kc)} comuni, {len(ka)} agenzie, {len(new_events)} nuovi eventi.')

if __name__=='__main__':main()
