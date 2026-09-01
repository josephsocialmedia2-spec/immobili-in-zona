#!/usr/bin/env python3
"""Ripulisce work_queue.csv prima del giro operativo.

Obiettivo: impedire che pagine categoria/ricerca, risultati non azionabili o
comuni fuori dal territorio F1 attivo entrino in giro_acquisizione.csv.
Lo storico/Market Intelligence resta nello state e non viene cancellato.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "data" / "work_queue.csv"
REJECTED = ROOT / "data" / "work_queue_rejected.csv"
MUNICIPALITIES = ROOT / "municipalities.csv"

CATEGORY_HOST_RULES = {
    "subito.it": [r"/annunci-[^/]+/(?:vendita|affitto)/(?:immobili|appartamenti|case|uffici|negozi)/"],
    "www.subito.it": [r"/annunci-[^/]+/(?:vendita|affitto)/(?:immobili|appartamenti|case|uffici|negozi)/"],
    "case.trovit.it": [r"^/[^/]+/?$"],
    "www.trovit.it": [r"^/[^/]+/?$"],
    "www.clickcase.it": [r"/annunci/(?:vendita|affitto)-case-privati-[^/]+\.html$"],
    "clickcase.it": [r"/annunci/(?:vendita|affitto)-case-privati-[^/]+\.html$"],
    "www.nuroa.it": [r"/(?:vendita|affitto)-immobili/[^/]+/?$"],
    "nuroa.it": [r"/(?:vendita|affitto)-immobili/[^/]+/?$"],
}

GENERIC_CATEGORY_TERMS = (
    "case in vendita", "appartamenti in vendita", "immobili in vendita",
    "case in affitto", "appartamenti in affitto", "immobili in affitto",
)

KNOWN_DETAIL_PATTERNS = (
    r"immobiliare\.it/annunci/\d+",
    r"trovacasa\.it/annunci/[^/]+-\d+",
    r"subito\.it/.+\.htm(?:$|[?#])",
)


def active_towns() -> set[str]:
    if not MUNICIPALITIES.exists():
        raise SystemExit("SANITIZE QUEUE: municipalities.csv assente")
    with MUNICIPALITIES.open("r", encoding="utf-8-sig", newline="") as f:
        towns = {
            (r.get("comune") or "").strip().casefold()
            for r in csv.DictReader(f)
            if (r.get("enabled") or "").strip() == "1" and (r.get("comune") or "").strip()
        }
    if "susa" not in towns:
        raise SystemExit("SANITIZE QUEUE: territorio non valido, Susa deve essere attiva")
    return towns


def is_detail_url(url: str) -> bool:
    return any(re.search(p, url or "", re.I) for p in KNOWN_DETAIL_PATTERNS)


def is_category_url(url: str) -> bool:
    if not url:
        return True
    if is_detail_url(url):
        return False
    p = urlparse(url)
    host = p.netloc.casefold()
    path = p.path.casefold()
    for pattern in CATEGORY_HOST_RULES.get(host, []):
        if re.search(pattern, path, re.I):
            return True
    return False


def reason(row: dict, allowed_towns: set[str]) -> str:
    town = (row.get("COMUNE") or "").strip().casefold()
    if not town or town not in allowed_towns:
        return "COMUNE_FUORI_TERRITORIO_F1"
    url = (row.get("URL") or "").strip()
    title = (row.get("TITOLO") or "").strip().casefold()
    if is_category_url(url):
        return "PAGINA_CATEGORIA_O_RICERCA"
    if any(term in title for term in GENERIC_CATEGORY_TERMS) and not is_detail_url(url):
        return "TITOLO_CATEGORIA_NON_OPERATIVO"
    return ""


def main() -> None:
    if not QUEUE.exists():
        print("SANITIZE QUEUE: work_queue.csv assente")
        return

    allowed_towns = active_towns()
    with QUEUE.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames or []

    kept, rejected = [], []
    for row in rows:
        why = reason(row, allowed_towns)
        if why:
            out = dict(row)
            out["MOTIVO_SCARTO_OPERATIVO"] = why
            rejected.append(out)
        else:
            kept.append(row)

    with QUEUE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(kept)

    rejected_fields = fields + (["MOTIVO_SCARTO_OPERATIVO"] if "MOTIVO_SCARTO_OPERATIVO" not in fields else [])
    with REJECTED.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rejected_fields)
        w.writeheader()
        w.writerows(rejected)

    print(
        f"SANITIZE QUEUE: {len(rows)} totali -> {len(kept)} operativi, "
        f"{len(rejected)} scartati; territorio F1={len(allowed_towns)} comuni attivi"
    )


if __name__ == "__main__":
    main()
