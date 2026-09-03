#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import csv, json, os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
INPUT=ROOT/'edilizia_results'
OUT=DATA/'municipal_edilizia_radar.csv'
SUMMARY=DATA/'municipal_edilizia_summary.json'
PREV=OUT
FIELDS=[
'DOC_ID','MASTER_660_ID','COMUNE','INDIRIZZO_SEGNALE','TIPOLOGIA_IMMOBILE','MATCH_INDIRIZZO',
'NATURA_ATTO','PRATICHE_RILEVATE','TITOLO_DOCUMENTO','ESTRATTO_PUBBLICO','URL_DOCUMENTO',
'FONTE_HOST','LETTURA','RILEVATO_IL','NOVITA_EDILIZIA','QUERY','NOTA'
]

def now(): return datetime.now(timezone.utc).isoformat()
def read_csv(path):
    if not path.exists(): return []
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

old={r.get('DOC_ID',''):r for r in read_csv(PREV) if r.get('DOC_ID')}
merged=dict(old)
new_ids=set()
workers=0
for p in sorted(INPUT.rglob('*.json')) if INPUT.exists() else []:
    try: doc=json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        print('SKIP',p,e);continue
    workers+=1
    for r in doc.get('documents') or []:
        did=r.get('DOC_ID')
        if not did: continue
        if did not in old:new_ids.add(did)
        merged[did]={**r,'NOVITA_EDILIZIA':'SI' if did in new_ids else 'NO'}

rows=list(merged.values())
for r in rows:
    if r.get('DOC_ID') not in new_ids and not r.get('NOVITA_EDILIZIA'):
        r['NOVITA_EDILIZIA']='NO'
    if isinstance(r.get('PRATICHE_RILEVATE'),list):
        r['PRATICHE_RILEVATE']=' | '.join(r['PRATICHE_RILEVATE'])
rows.sort(key=lambda r:(str(r.get('COMUNE','')).casefold(),int(r.get('MASTER_660_ID') or 999999),str(r.get('NATURA_ATTO','')),str(r.get('URL_DOCUMENTO',''))))
DATA.mkdir(parents=True,exist_ok=True)
with OUT.open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore');w.writeheader();w.writerows(rows)
by_nature=Counter(r.get('NATURA_ATTO') or 'NON_CLASSIFICATO' for r in rows)
by_match=Counter(r.get('MATCH_INDIRIZZO') or 'NON_CLASSIFICATO' for r in rows)
summary={
'generated_at':now(),'workers':workers,'documents_total':len(rows),'novita_edilizia':len(new_ids),
'master_con_documenti':len({r.get('MASTER_660_ID') for r in rows if r.get('MASTER_660_ID')}),
'per_natura':dict(by_nature),'per_match':dict(by_match),
'policy':'PUBLIC_MUNICIPAL_BUILDING_ACTS_NO_PERSONAL_DATA_NO_OWNER_INFERENCE'
}
SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"PASS MERGE EDILIZIA | worker={workers} | documenti={len(rows)} | novita={len(new_ids)} | master_match={summary['master_con_documenti']}")
