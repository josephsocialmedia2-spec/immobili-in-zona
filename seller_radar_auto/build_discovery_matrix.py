#!/usr/bin/env python3
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MUNICIPALITIES = ROOT / "municipalities.csv"
LOCALITIES = ROOT / "territory_localities.csv"

def yes(v):
    return str(v or "").strip().lower() in {"1","true","yes","y"}

targets = []
seen = set()

with MUNICIPALITIES.open(encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        comune = (r.get("comune") or "").strip()
        if not comune or not yes(r.get("enabled")):
            continue
        key = ("COMUNE", comune.casefold())
        if key not in seen:
            seen.add(key)
            targets.append({"tipo":"COMUNE","comune":comune,"localita":""})

if LOCALITIES.exists():
    with LOCALITIES.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if not yes(r.get("enabled")):
                continue
            comune = (r.get("comune") or "").strip()
            localita = (r.get("localita") or "").strip()
            tipo = (r.get("tipo") or "LOCALITA").strip().upper()
            if not comune or not localita:
                continue
            key = (tipo, comune.casefold(), localita.casefold())
            if key not in seen:
                seen.add(key)
                targets.append({"tipo":tipo,"comune":comune,"localita":localita})

out = ROOT / "data" / "discovery_matrix.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({"targets":targets}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"targets":len(targets)}, ensure_ascii=False))
