#!/usr/bin/env python3
import csv, json
from pathlib import Path
p=Path(__file__).resolve().parent/"municipalities.csv"
with p.open(encoding="utf-8-sig",newline="") as f:
    comuni=[(r.get("comune") or "").strip() for r in csv.DictReader(f) if r.get("enabled")=="1" and (r.get("comune") or "").strip()]
print(json.dumps({"comune":comuni},ensure_ascii=False,separators=(",",":")))
