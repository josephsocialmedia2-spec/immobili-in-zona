#!/usr/bin/env python3
"""Stampa una matrix JSON GitHub Actions per gli URL trovati nel ciclo corrente."""
import hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
INPUT=ROOT/"discovery_results"

def key(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()[:20]
ids=[]; seen=set()
for path in sorted(INPUT.rglob("*.json")) if INPUT.exists() else []:
    try: doc=json.loads(path.read_text(encoding="utf-8"))
    except Exception: continue
    for r in doc.get("results") or []:
        url=(r.get("url") or "").strip()
        if not url: continue
        i=key(url)
        if i not in seen:
            seen.add(i); ids.append(i)
print(json.dumps({"item_id":ids[:80]},separators=(",",":")))
