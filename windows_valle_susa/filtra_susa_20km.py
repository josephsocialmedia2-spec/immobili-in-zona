#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Filtra la lista locale dei contatti sul perimetro unico Susa 20 km.

Non crea un secondo pannello: produce soltanto il CSV intermedio che alimenta
F1 Centrale Telefonate Guidate. I dati personali restano sul PC.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "seller_radar_auto" / "f1_microzone_config.json"
BASE = Path.home() / "Documents" / "F1_Directory_Microzone"
DATA = BASE / "data"
SOURCE = DATA / "telefonate_mattino.csv"
OUT = DATA / "telefonate_susa_20km.csv"
SUMMARY = BASE / "PERIMETRO_SUSA_20KM.txt"


def norm(value: str) -> str:
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", s.casefold()).strip()


def row_town(row: dict) -> str:
    for key in ("COMUNE", "RADAR_COMUNE", "Comune", "comune"):
        v = str(row.get(key) or "").strip()
        if v:
            return v
    return ""


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    towns = [str(x).strip() for x in cfg.get("priority_towns", []) if str(x).strip()]
    allowed = {norm(x): i for i, x in enumerate(towns)}
    if cfg.get("priority_center") != "Susa" or int(cfg.get("priority_radius_km", 0)) != 20:
        raise SystemExit("Configurazione non coerente: richiesto centro Susa, raggio 20 km")
    if not SOURCE.exists():
        raise SystemExit(f"Lista locale non trovata: {SOURCE}")

    with SOURCE.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = [r for r in reader if norm(row_town(r)) in allowed]

    rows.sort(key=lambda r: (
        allowed.get(norm(row_town(r)), 999),
        norm(r.get("VIA_TARGET") or r.get("RADAR_DOVE_ANDRE") or ""),
        norm(r.get("NOME") or ""),
        norm(r.get("TELEFONO") or ""),
    ))

    DATA.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    SUMMARY.write_text(
        "F1 — PERIMETRO OPERATIVO UNICO\n"
        "Centro: Susa\n"
        "Raggio: 20 km\n"
        "Comuni attivi: " + ", ".join(towns) + "\n"
        f"Contatti microzona nel perimetro: {len(rows)}\n"
        f"CSV intermedio: {OUT}\n"
        "Output chiamate: F1_CENTRALE_TELEFONATE_GUIDATE.html\n",
        encoding="utf-8",
    )
    print(f"SUSA 20 KM: {len(rows)} contatti microzona ammessi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
