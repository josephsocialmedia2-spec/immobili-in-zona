#!/usr/bin/env python3
"""Validazione fail-closed del Giro F1.

Il Market Intelligence può contenere storico fuori zona. Il Giro operativo no:
usa esclusivamente i comuni enabled=1 in municipalities.csv e deve partire da
un territorio con Susa attiva.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MUNICIPALITIES = ROOT / "municipalities.csv"
GIRO = DATA / "giro_acquisizione.csv"
TEAM = DATA / "giro_funzionari.csv"
TEAM_JSON = DATA / "giro_funzionari.json"


def norm(value: object) -> str:
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"FAIL: file mancante: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def allowed_towns() -> set[str]:
    rows = load_csv(MUNICIPALITIES)
    towns = {
        norm(r.get("comune"))
        for r in rows
        if (r.get("enabled") or "").strip() == "1" and norm(r.get("comune"))
    }
    if "susa" not in towns:
        raise SystemExit("FAIL: Susa non è attiva nel territorio F1")
    return towns


def assert_towns(rows: list[dict], allowed: set[str], label: str) -> None:
    outside = sorted({
        (r.get("COMUNE") or "").strip()
        for r in rows
        if norm(r.get("COMUNE")) not in allowed
    })
    if outside:
        raise SystemExit(f"FAIL {label}: comuni fuori territorio: {outside}")


def main() -> int:
    allowed = allowed_towns()
    giro = load_csv(GIRO)
    team = load_csv(TEAM)
    assert_towns(giro, allowed, "GIRO")
    assert_towns(team, allowed, "TEAM")

    giro_urls = {(r.get("URL") or "").strip() for r in giro if (r.get("URL") or "").strip()}
    foreign_team_urls = sorted({
        (r.get("URL") or "").strip()
        for r in team
        if (r.get("URL") or "").strip() and (r.get("URL") or "").strip() not in giro_urls
    })
    if foreign_team_urls:
        raise SystemExit(f"FAIL TEAM: {len(foreign_team_urls)} righe non presenti nel Giro")

    disabled_known = {
        norm(r.get("comune"))
        for r in load_csv(MUNICIPALITIES)
        if (r.get("enabled") or "").strip() != "1" and norm(r.get("comune"))
    }
    leaked_disabled = sorted({
        (r.get("COMUNE") or "").strip()
        for r in giro
        if norm(r.get("COMUNE")) in disabled_known
    })
    if leaked_disabled:
        raise SystemExit(f"FAIL GIRO: comuni disabled presenti: {leaked_disabled}")

    if TEAM_JSON.exists():
        meta = json.loads(TEAM_JSON.read_text(encoding="utf-8"))
        declared = {norm(x) for x in (meta.get("territory_active_towns") or []) if norm(x)}
        if declared and declared != allowed:
            raise SystemExit("FAIL TEAM JSON: territorio dichiarato diverso da municipalities.csv")

    towns_in_giro = sorted({(r.get("COMUNE") or "").strip() for r in giro if (r.get("COMUNE") or "").strip()})
    print(
        f"PASS GIRO F1 | righe={len(giro)} | team={len(team)} | "
        f"comuni_operativi={len(towns_in_giro)}/{len(allowed)} | centro=Susa"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
