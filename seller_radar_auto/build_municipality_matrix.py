#!/usr/bin/env python3
"""Genera la matrix di discovery MASTER.

La colonna `enabled` di municipalities.csv definisce il territorio operativo
(Giro di oggi), non ciò che il Seller Radar deve conservare/monitorare. La
matrix di discovery comprende quindi tutti i comuni catalogati: prima quelli
prioritari configurati, poi gli altri nell'ordine del CSV.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MUNICIPALITIES = ROOT / "municipalities.csv"
CONFIG = ROOT / "f1_microzone_config.json"

cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
priority = [str(x).strip() for x in cfg.get("priority_towns", []) if str(x).strip()]

with MUNICIPALITIES.open(encoding="utf-8-sig", newline="") as f:
    catalog = [
        (r.get("comune") or "").strip()
        for r in csv.DictReader(f)
        if (r.get("comune") or "").strip()
    ]

if not catalog:
    raise SystemExit("Catalogo comuni vuoto: impossibile generare la discovery master")

by_key = {comune.casefold(): comune for comune in catalog}
comuni = []
seen = set()

# Mantiene Susa e le priorità all'inizio della matrix, senza perdere gli altri
# territori che devono continuare a essere monitorati nel database master.
for comune in priority + catalog:
    key = comune.casefold()
    canonical = by_key.get(key)
    if not canonical or key in seen:
        continue
    seen.add(key)
    comuni.append(canonical)

if "susa" not in seen:
    raise SystemExit("Configurazione territorio non valida: Susa manca dal catalogo master")

# Susa resta il primo centro di riferimento della matrix.
susa_idx = next(i for i, comune in enumerate(comuni) if comune.casefold() == "susa")
if susa_idx:
    comuni.insert(0, comuni.pop(susa_idx))

print(json.dumps({"comune": comuni}, ensure_ascii=False, separators=(",", ":")))
