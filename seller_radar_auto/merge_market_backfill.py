#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATE=ROOT/'data'/'state.json'; INPUT=ROOT/'market_backfill_results'
try: state=json.loads(STATE.read_text(encoding='utf-8'))
except Exception: state={'items':{}}
items=state.get('items') or {}; merged=0
for p in sorted(INPUT.rglob('*.json')) if INPUT.exists() else []:
    try: doc=json.loads(p.read_text(encoding='utf-8'))
    except Exception: continue
    i=(doc.get('item_id') or '').strip(); x=items.get(i)
    if not x: continue
    e=doc.get('enrichment') or {}; area=doc.get('area') or {}
    keep=x.get('enrichment') or {}
    for k in ('checked_at','listing_fetch','address_hints','seller_name','seller_confidence','seller_source','detected_price','price_confidence','price_source','price_evidence_count','cross_matches','cross_match_count'):
        if k in e: keep[k]=e[k]
    x['enrichment']=keep
    old_area=x.get('area_radar') or {}
    if area.get('reference_addresses'): old_area['reference_addresses']=area['reference_addresses']
    if area.get('street'): old_area['street']=area['street']
    x['area_radar']=old_area; merged+=1
state['items']=items
STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'MARKET BACKFILL MERGE: {merged} annunci aggiornati')
