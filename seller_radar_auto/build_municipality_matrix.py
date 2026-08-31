#!/usr/bin/env python3
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MUNICIPALITIES = ROOT / "municipalities.csv"
CONFIG = ROOT / "f1_microzone_config.json"

cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
priority = [str(x).strip() for x in cfg.get("priority_towns", []) if str(x).strip()]

with MUNICIPALITIES.open(encoding="utf-8-sig", newline="") as f:
    enabled = {
        (r.get("comune") or "").strip().casefold(): (r.get("comune") or "").strip()
        for r in csv.DictReader(f)
        if r.get("enabled") == "1" and (r.get("comune") or "").strip()
    }

# Regola unica: il primo ufficio e Susa. Il Radar non allarga piu la matrix
# agli altri territori: elabora solo i comuni esplicitamente ammessi nel
# perimetro operativo Susa 20 km, nell'ordine definito dalla configurazione.
comuni = []
seen = set()
for comune in priority:
    key = comune.casefold()
    if key in seen or key not in enabled:
        continue
    seen.add(key)
    comuni.append(enabled[key])

if not comuni or comuni[0].casefold() != "susa":
    raise SystemExit("Configurazione territorio non valida: Susa deve essere il centro operativo")

print(json.dumps({"comune": comuni}, ensure_ascii=False, separators=(",", ":")))
