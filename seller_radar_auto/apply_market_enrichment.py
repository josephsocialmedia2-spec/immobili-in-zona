#!/usr/bin/env python3
"""Applica allo storico solo prezzi e inserzionisti con confidenza sufficiente."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'data'/'state.json'
VALID_CONF={'HIGH','MEDIUM'}


def iso_now(): return datetime.now(timezone.utc).isoformat()
def valid_price(v):
    try:
        n=int(float(v))
        return n if 5000<=n<=20_000_000 else None
    except Exception:return None

try:
    state=json.loads(STATE.read_text(encoding='utf-8'))
except Exception as exc:
    raise SystemExit(f'state non leggibile: {exc}')

items=state.get('items') or {}; prices_added=0; sellers_verified=0; sellers_review=0
for x in items.values():
    e=x.get('enrichment') or {}; conf=str(e.get('price_confidence') or '').upper(); p=valid_price(e.get('detected_price'))
    if p and conf in VALID_CONF:
        hist=x.setdefault('price_history',[])
        if not hist or valid_price(hist[-1].get('price'))!=p:
            hist.append({'at':e.get('checked_at') or iso_now(),'price':p,'source':e.get('price_source') or 'PAGE_ENRICHMENT','confidence':conf})
            x['price_history']=hist[-30:]; prices_added+=1
        x['last_verified_price']=p; x['last_price_confidence']=conf; x['last_price_source']=e.get('price_source','')
    s=(e.get('seller_name') or '').strip(); sconf=str(e.get('seller_confidence') or '').upper()
    if s and sconf in VALID_CONF:
        x['seller_name_verified']=s; x['seller_confidence']=sconf; sellers_verified+=1
    elif s and sconf and sconf not in VALID_CONF:
        e['seller_name_review']=s; e['seller_name']=''; sellers_review+=1
        x['enrichment']=e

state['items']=items; state['market_enrichment_updated_at']=iso_now()
STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'MARKET ENRICHMENT: prezzi aggiunti={prices_added}, seller verificati={sellers_verified}, seller review esclusi={sellers_review}')
