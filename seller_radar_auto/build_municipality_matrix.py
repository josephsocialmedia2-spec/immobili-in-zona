#!/usr/bin/env python3
"""Genera la matrix di discovery sul solo territorio operativo abilitato.

La colonna `enabled` di municipalities.csv e' la fonte canonica del perimetro.
Solo i comuni con enabled=1 entrano nella discovery, incluse tutte le fonti
(portali, Facebook Marketplace, gruppi Facebook, web e bacheche locali).
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MUNICIPALITIES = ROOT / "municipalities.csv"

with MUNICIPALITIES.open(encoding="utf-8-sig", newline="") as f:
    comuni = [
        (r.get("comune") or "").strip()
        for r in csv.DictReader(f)
        if (r.get("comune") or "").strip()
        and str(r.get("enabled") or "").strip().lower() in {"1", "true", "yes", "y"}
    ]

if not comuni:
    raise SystemExit("Nessun comune operativo abilitato in municipalities.csv")

# Deduplica mantenendo l'ordine operativo del CSV.
out = []
seen = set()
for comune in comuni:
    key = comune.casefold()
    if key in seen:
        continue
    seen.add(key)
    out.append(comune)

print(json.dumps({"comune": out}, ensure_ascii=False, separators=(",", ":")))
