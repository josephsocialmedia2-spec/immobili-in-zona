#!/usr/bin/env python3
"""Fallback Dork per prezzo/agenzia quando il portale blocca la lettura diretta."""
import json, os, re
from pathlib import Path
from urllib.parse import urlparse
from search_engine import search

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'data'/'state.json'
ITEM_ID=os.getenv('F1_ITEM_ID','').strip()
OUT=Path(os.getenv('F1_ITEM_OUT',str(ROOT/'data'/'item_result.json')))
PRICE_RE=re.compile(r'(?:€|EUR\b|euro\b)\s*([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})|([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})\s*(?:€|EUR\b|euro\b)',re.I)
ADDR_RE=re.compile(r'\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo|localit[aà])\s+[A-Za-zÀ-ÿ0-9\'’ .,-]{2,80}?\s+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|[A-Za-z])?\b',re.I)
PROP_RE=re.compile(r'\b(villa|villetta|appartamento|trilocale|bilocale|quadrilocale|rustico|casale|casa indipendente|terratetto|attico|mansarda|terreno)\b',re.I)
BAD_SELLERS={'idealista','immobiliare.it','casa.it','subito','trovit','wikicasa','tecnocasa','tecnorete','tempocasa','gabetti'}

def fold(s):return re.sub(r'[^a-z0-9à-ÿ]+',' ',str(s or '').casefold()).strip()
def host(u):return urlparse(u or '').netloc.lower().removeprefix('www.')
def listing_id(u):
    nums=re.findall(r'(?<!\d)(\d{6,12})(?!\d)',urlparse(u or '').path)
    return nums[-1] if nums else ''
def amount(v):
    d=re.sub(r'\D','',v or '')
    if not d:return None
    n=int(d);return n if 5000<=n<=20_000_000 else None
def prices(text):
    out=[]
    for m in PRICE_RE.finditer(text or ''):
        n=amount(m.group(1) or m.group(2))
        if n and n not in out:out.append(n)
    return out
def seller(text):
    pats=[r'\b([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&\'’ .-]{2,70}\s+Immobiliare)\b',r'\b(RE/?MAX\s+[A-Za-zÀ-ÿ0-9&\'’ .-]{2,70})\b',r'\b([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&\'’ .-]{2,70})\s+(?:propone|presenta)\b']
    for p in pats:
        m=re.search(p,text or '',re.I)
        if m:
            v=re.sub(r'\s+',' ',m.group(1)).strip(' -,.')
            if 3<=len(v)<=100 and v.casefold() not in BAD_SELLERS and 'privato' not in v.casefold():return v
    return ''
def addr_from(text):
    m=ADDR_RE.search(text or '')
    return re.sub(r'\s+',' ',m.group(0)).strip(' ,.;') if m else ''
def address_parts(address):
    a=fold(address);m=re.search(r'\b(\d{1,4})\b',a);civ=m.group(1) if m else ''
    street=re.sub(r'\b\d{1,4}\b.*$','',a).strip()
    return street,civ
def score(item,r,address):
    text=f"{r.get('title','')} {r.get('snippet','')}";ft=fold(text);s=0
    src=(r.get('url') or '').rstrip('/');orig=(item.get('url') or '').rstrip('/')
    exact=src==orig; same_host=bool(host(orig) and host(orig)==host(src)); lid=listing_id(orig)
    if exact:s+=140
    if lid and (lid in src or lid in text):s+=100
    street,civ=address_parts(address)
    if address and fold(address) in ft:s+=65
    else:
        if street and street in ft:s+=35
        if civ and re.search(rf'\b{re.escape(civ)}\b',ft):s+=25
    if fold(item.get('comune','')) and fold(item.get('comune','')) in ft:s+=20
    if same_host:s+=20
    a={x.casefold() for x in PROP_RE.findall(item.get('title',''))};b={x.casefold() for x in PROP_RE.findall(text)}
    if a and b:s+=15
    return s,exact,same_host

if not ITEM_ID or not OUT.exists():raise SystemExit('item/output mancanti')
state=json.loads(STATE.read_text(encoding='utf-8'));x=(state.get('items') or {}).get(ITEM_ID)
if not x:raise SystemExit('item non trovato')
doc=json.loads(OUT.read_text(encoding='utf-8'));e=doc.setdefault('enrichment',{})
address=(e.get('address_hints') or [''])[0] or addr_from(f"{x.get('title','')} {x.get('snippet','')}")
comune=x.get('comune','');domain=host(x.get('url'));lid=listing_id(x.get('url'));pm=PROP_RE.search(x.get('title','') or '');ptype=pm.group(1) if pm else 'immobile'
private_hint=bool(x.get('private_intent')) or str(x.get('seller_hint','')).upper()=='INDIZIO_PRIVATO'
street,civ=address_parts(address)
title=re.sub(r'\s*[-–|]\s*(?:idealista|immobiliare\.it|casa\.it).*$', '', x.get('title',''), flags=re.I).strip()
queries=[]
# Prima le chiavi univoche dell'annuncio: sono molto più affidabili dell'indirizzo generico.
if lid:
    queries.append(f'"{lid}"')
    if domain:queries.append(f'site:{domain} "{lid}"')
if title:queries.append(f'"{title}"')
if address:
    if domain:queries.append(f'site:{domain} "{comune}" "{address}"')
    queries.append(f'"{address}" "{comune}" "{ptype}"')
    if street and civ:queries.append(f'"{street}" {civ} "{comune}" {ptype}')
    if not private_hint:queries.append(f'"{address}" "{comune}" (agenzia OR immobiliare OR propone)')
else:
    queries.append(f'"{comune}" "{ptype}" "{title[:70]}"')
# dedup query mantenendo l'ordine
queries=list(dict.fromkeys(q for q in queries if q.strip()))[:7]

matches=[];best_price=None;best_p_score=-1;best_seller='';best_s_score=-1;query_log=[]
for q in queries:
    results,err=search(q,15);query_log.append({'q':q,'error':err,'results':len(results)})
    for r in results:
        sc,exact,same_host=score(x,r,address)
        if sc<55:continue
        text=f"{r.get('title','')} {r.get('snippet','')}";ps=prices(text);sn=seller(text)
        matches.append({'q':q,'url':r.get('url',''),'title':r.get('title',''),'snippet':r.get('snippet',''),'score':sc,'exact_url':exact,'same_host':same_host,'prices':ps,'seller':sn})
        if ps and sc>best_p_score:best_price=ps[0];best_p_score=sc
        seller_ok=(not private_hint) and sn and (exact or (same_host and sc>=115))
        if seller_ok and sc>best_s_score:best_seller=sn;best_s_score=sc

if best_price and str(e.get('price_confidence','')).upper() not in {'HIGH','MEDIUM'}:
    e['detected_price']=best_price;e['price_confidence']='HIGH' if best_p_score>=120 else 'MEDIUM';e['price_source']='DORK_FALLBACK';e['price_evidence_count']=sum(best_price in m.get('prices',[]) for m in matches)
if best_seller and str(e.get('seller_confidence','')).upper() not in {'HIGH','MEDIUM'}:
    e['seller_name']=best_seller;e['seller_confidence']='HIGH' if best_s_score>=140 else 'MEDIUM';e['seller_source']='DORK_FALLBACK'
e['fallback_queries']=query_log;e['fallback_matches']=sorted(matches,key=lambda z:z['score'],reverse=True)[:12]
e['fallback_private_protection']=private_hint
e['fallback_listing_id']=lid
OUT.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"FALLBACK {ITEM_ID}: id={lid or '-'} address={address or '-'} price={e.get('detected_price') or '-'}({e.get('price_confidence','NONE')}) seller={e.get('seller_name') or '-'} private={private_hint} matches={len(matches)} queries={[(z['results'],z['error']) for z in query_log]}")
