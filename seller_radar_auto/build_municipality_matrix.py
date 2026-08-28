#!/usr/bin/env python3
import csv, json
from pathlib import Path

p = Path(__file__).resolve().parent / "municipalities.csv"
priority = [
    "Susa",
    "Mompantero",
    "Meana di Susa",
    "Gravere",
    "Giaglione",
    "Venaus",
    "Mattie",
    "Chiomonte",
    "Novalesa",
    "Bussoleno",
    "Chianocco",
    "San Giorio di Susa",
    "Moncenisio",
]

with p.open(encoding="utf-8-sig", newline="") as f:
    enabled = [
        (r.get("comune") or "").strip()
        for r in csv.DictReader(f)
        if r.get("enabled") == "1" and (r.get("comune") or "").strip()
    ]

# Prima Susa + raggio 10 km nell'ordine operativo definito; poi tutti gli altri.
seen = set()
comuni = []
for comune in priority + enabled:
    key = comune.casefold()
    if key in seen:
        continue
    if comune not in enabled:
        continue
    seen.add(key)
    comuni.append(comune)

print(json.dumps({"comune": comuni}, ensure_ascii=False, separators=(",", ":")))
