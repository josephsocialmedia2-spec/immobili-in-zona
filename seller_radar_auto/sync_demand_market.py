#!/usr/bin/env python3
"""Sync Seller Radar residential opportunities into F1 Demand Engine.

Security model: this script uses only the public Supabase publishable key and can
INSERT public market opportunities. It cannot read buyer requests or PII.
"""
from __future__ import annotations

import csv
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent / "data" / "giro_acquisizione.csv"
SUPABASE_URL = "https://nqnmlsmeiynxbdojeyjt.supabase.co"
PUBLISHABLE_KEY = "sb_publishable_Clz5qPTkTtvwV0rqWTcfMQ_sCDSRgnu"
ENDPOINT = f"{SUPABASE_URL}/rest/v1/f1_market_opportunities"
ALLOWED_HOSTS = {
    "immobiliare.it", "www.immobiliare.it",
    "idealista.it", "www.idealista.it",
    "subito.it", "www.subito.it",
    "casa.it", "www.casa.it",
    "trovacasa.it", "www.trovacasa.it",
    "trovit.it", "case.trovit.it", "www.trovit.it",
    "clickcase.it", "www.clickcase.it",
    "bakeca.it", "torino.bakeca.it", "www.bakeca.it",
    "nuroa.it", "www.nuroa.it",
}


def clean(value: object) -> str:
    return str(value or "").strip()


def valid_url(value: str) -> bool:
    try:
        u = urllib.parse.urlparse(value)
        return u.scheme == "https" and (u.hostname or "").lower() in ALLOWED_HOSTS
    except Exception:
        return False


def parse_price(value: str):
    s = clean(value).upper()
    if not s or "VERIFICARE" in s or "N.D" in s or "ND" == s:
        return None
    digits = re.sub(r"[^0-9,\.]", "", s)
    if not digits:
        return None
    if "," in digits and "." in digits:
        digits = digits.replace(".", "").replace(",", ".")
    elif digits.count(".") > 1:
        digits = digits.replace(".", "")
    elif digits.count(",") > 1:
        digits = digits.replace(",", "")
    else:
        digits = digits.replace(",", ".")
    try:
        n = float(digits)
        return n if n > 0 else None
    except ValueError:
        return None


def infer_type(title: str) -> str | None:
    t = title.lower()
    rules = [
        ("casa indipendente", ("casa indipendente", "indipendente")),
        ("semindipendente", ("semindipendente", "semi indipendente")),
        ("appartamento", ("appartamento", "trilocale", "bilocale", "quadrilocale", "monolocale")),
        ("villa", ("villa", "villetta")),
        ("rustico", ("rustico", "casale", "cascina")),
    ]
    for label, words in rules:
        if any(w in t for w in words):
            return label
    return None


def to_int(value: str):
    try:
        return int(float(clean(value)))
    except Exception:
        return None


def build_rows() -> list[dict]:
    if not CSV_PATH.exists():
        raise SystemExit(f"CSV non trovato: {CSV_PATH}")
    rows: list[dict] = []
    seen: set[str] = set()
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if clean(r.get("TIPO_OPPORTUNITA")).upper() != "RESIDENZIALE":
                continue
            url = clean(r.get("URL"))
            comune = clean(r.get("COMUNE"))
            source = clean(r.get("FONTE")) or "Seller Radar"
            title = clean(r.get("COSA_CERCO"))
            if not comune or not valid_url(url) or url in seen:
                continue
            seen.add(url)
            rows.append({
                "source_name": source[:120],
                "source_url": url,
                "external_id": None,
                "comune": comune[:120],
                "indirizzo_zona": (clean(r.get("DOVE_ANDRE")) or None),
                "prezzo": parse_price(clean(r.get("PREZZO"))),
                "tipologia": infer_type(title),
                "raw_title": title[:500] or None,
                "radar_score": to_int(clean(r.get("SCORE"))),
                "radar_priority": clean(r.get("PRIORITA"))[:30] or None,
                "seller_signal": clean(r.get("SELLER_SIGNAL"))[:120] or None,
                "stato_annuncio": "ATTIVO",
            })
    return rows


def post_one(row: dict) -> str:
    data = json.dumps(row, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=data,
        method="POST",
        headers={
            "apikey": PUBLISHABLE_KEY,
            "Authorization": f"Bearer {PUBLISHABLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            if res.status not in (200, 201, 204):
                raise RuntimeError(f"Supabase HTTP {res.status}")
            return "inserted"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        # 23505 = duplicate source_url. Ignore without requesting SELECT rights.
        if e.code == 409 and ('23505' in body or 'duplicate key' in body.lower()):
            return "duplicate"
        raise RuntimeError(f"Supabase HTTP {e.code}: {body}") from e


def main() -> int:
    rows = build_rows()
    if not rows:
        print("F1 Demand sync: nessuna opportunità residenziale valida da sincronizzare.")
        return 0
    inserted = duplicate = 0
    for row in rows:
        result = post_one(row)
        inserted += result == "inserted"
        duplicate += result == "duplicate"
    print(f"F1 Demand sync: {inserted} nuove opportunità inserite; {duplicate} duplicati ignorati; {len(rows)} candidate valide.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
