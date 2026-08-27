#!/usr/bin/env python3
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATE=ROOT/'data'/'state.json'
try: state=json.loads(STATE.read_text(encoding='utf-8'))
except Exception: state={'items':{}}
rows=[]
for i,x in (state.get('items') or {}).items():
    if str(x.get('lifecycle','')).upper() not in {'NEW','TRACKED','RELISTED'}: continue
    url=(x.get('url') or '').lower(); title=(x.get('title') or '').lower(); e=x.get('enrichment') or {}
    listing=bool(re.search(r'/(annunci|annuncio|immobile|property|listing)/|/p\d{6,}',url)) or bool(re.search(r'\b(villa|appartamento|trilocale|bilocale|quadrilocale|rustico|casa indipendente|attico|mansarda|terreno)\b.*\b(vendita|in vendita)\b',title))
    broad=bool(re.search(r'\b\d+[\d.]*\s+immobili in vendita|case e appartamenti a|immobili in vendita a\b',title))
    if not listing or broad: continue
    needs_price=not (x.get('price_history') or [])
    needs_seller=not (e.get('seller_name') or x.get('seller_name_verified'))
    if not (needs_price or needs_seller): continue
    score=(3 if needs_price else 0)+(2 if needs_seller else 0)+(2 if any(p in url for p in ('immobiliare.it/annunci/','idealista.it/immobile/','casa.it/immobili/')) else 0)
    rows.append((score,i))
rows.sort(reverse=True)
print(json.dumps({'item_id':[i for _,i in rows[:40]] or ['__NONE__']},separators=(',',':')))
