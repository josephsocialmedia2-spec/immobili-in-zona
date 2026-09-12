#!/usr/bin/env python3
"""Genera la matrix di discovery sul territorio operativo Villar Dora.

municipalities.csv è il perimetro operativo del Seller Radar sorgente.
Regole obbligatorie:
- Villar Dora è l'unico CENTRO;
- ogni altro comune abilitato è SINISTRA o DESTRA;
- radial_rank è univoco e determina l'ordine operativo;
- i comuni disabilitati sono fuori perimetro e non entrano nella discovery.

L'output mantiene la forma storica {"comune":[...]} perché è consumata da
più workflow GitHub; lato e radial_rank restano nella fonte municipalities.csv
e vengono persistiti negli item durante il merge della discovery.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MUNICIPALITIES = ROOT / "municipalities.csv"

rows=[]
with MUNICIPALITIES.open(encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        comune=(r.get("comune") or "").strip()
        enabled=str(r.get("enabled") or "").strip().lower() in {"1","true","yes","y"}
        if not comune or not enabled:
            continue
        side=(r.get("side") or "").strip().upper()
        try: rank=int(r.get("radial_rank") or 9999)
        except Exception: rank=9999
        if side not in {"CENTRO","SINISTRA","DESTRA"}:
            raise SystemExit(f"Lato territoriale non valido per {comune}: {side or 'MANCANTE'}")
        rows.append({"comune":comune,"side":side,"radial_rank":rank})

if not rows:
    raise SystemExit("Nessun comune operativo abilitato in municipalities.csv")

centers=[r for r in rows if r["side"]=="CENTRO"]
if len(centers)!=1 or centers[0]["comune"].casefold()!="villar dora":
    raise SystemExit("Villar Dora deve essere l'unico CENTRO del Seller Radar")

seen_names=set(); seen_ranks=set()
for row in rows:
    key=row["comune"].casefold()
    if key in seen_names: raise SystemExit(f"Comune duplicato: {row['comune']}")
    if row["radial_rank"] in seen_ranks: raise SystemExit(f"radial_rank duplicato: {row['radial_rank']}")
    seen_names.add(key); seen_ranks.add(row["radial_rank"])

rows.sort(key=lambda r:(r["radial_rank"],r["comune"].casefold()))
print(json.dumps({"comune":[r["comune"] for r in rows]}, ensure_ascii=False, separators=(",", ":")))
