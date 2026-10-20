#!/usr/bin/env python3
import csv, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
Q=DATA/"work_queue.csv"
G=DATA/"giro_acquisizione.csv"
S=DATA/"giro_riepilogo.json"

def rows(p):
    if not p.exists(): return []
    with p.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

q=rows(Q); g=rows(G)
summary=json.loads(S.read_text(encoding="utf-8")) if S.exists() else {}
assert len(g)==len(q), f"MASTER NON PRESERVATO: queue={len(q)} giro={len(g)}"
urls_q=[r.get("URL","") for r in q]
urls_g=[r.get("URL","") for r in g]
assert sorted(urls_q)==sorted(urls_g), "URL master persi o duplicati nel giro"
assert summary.get("seller_master_totali")==len(q)
print(f"PASS GIRO QA | master={len(q)}")
