#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 — arricchimento telefonate per le vie del Giro Acquisizione.

Legge direttamente seller_radar_auto/data/giro_acquisizione.csv e usa ogni
fermata operativa "VAI IN ZONA" come chiave di ricerca. I contatti trovati
vengono aggiunti al file prospect_web_susa_20km.csv che alimenta la Centrale.

Regole:
- priorita alla via/civico realmente presenti nel Giro Seller Radar;
- solo contatti pubblicati su pagine web aperte di attivita/professionisti;
- nessun login, CAPTCHA bypass, PDF/atti PA o data broker;
- nessuna inferenza "numero = proprietario";
- ogni contatto conserva la URL fonte e resta soggetto a verifica RPO/privacy.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RADAR = REPO / "seller_radar_auto"
GIRO = RADAR / "data" / "giro_acquisizione.csv"
CONFIG = RADAR / "f1_microzone_config.json"

BASE = Path.home() / "Documents" / "F1_Directory_Microzone"
DATA = BASE / "data"
OUT = DATA / "prospect_web_susa_20km.csv"
LOG = BASE / "prospect_web_vie_giro.log"

sys.path.insert(0, str(HERE))
import prospect_susa_20km as base  # noqa: E402

MAX_RESULTS = int(os.getenv("F1_ROUTE_RESULTS_PER_QUERY", "6"))
MAX_PAGES_PER_STREET = int(os.getenv("F1_ROUTE_PAGES_PER_STREET", "8"))
MAX_STREETS = int(os.getenv("F1_ROUTE_MAX_STREETS", "80"))

FIELDS = [
    "PROSPECT_ID", "SCORE", "COMUNE", "NOME", "CATEGORIA", "TELEFONO", "EMAIL",
    "ALTRI_CONTATTI", "MOTIVO_CONTATTO", "SEGNALE_RADAR", "RADAR_SCORE", "RADAR_URL",
    "FONTE_CONTATTO", "URL_CONTATTO", "PUBBLICO", "RPO_STATUS", "STATO",
]


def log(message: str) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    base.log("VIE GIRO | " + message)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def norm(value: str) -> str:
    s = str(value or "").casefold()
    s = s.replace("à", "a").replace("è", "e").replace("é", "e").replace("ì", "i").replace("ò", "o").replace("ù", "u")
    s = s.replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def street_and_civic(address: str) -> tuple[str, str]:
    s = re.sub(r"\s+", " ", str(address or "")).strip(" ,.;")
    if not s or "indirizzo da verificare" in norm(s):
        return "", ""
    m = re.search(r"\s+(\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|\s*[A-Za-z])?)\s*$", s)
    civic = re.sub(r"\s+", "", m.group(1)) if m else ""
    street = s[:m.start()].strip(" ,.;") if m else s
    return street, civic


def score_value(row: dict) -> int:
    try:
        return int(float(str(row.get("SCORE") or "0").replace(",", ".")))
    except Exception:
        return 0


def route_stops() -> list[dict]:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    towns = [str(x).strip() for x in cfg.get("priority_towns", []) if str(x).strip()]
    town_rank = {norm(t): i for i, t in enumerate(towns)}
    rows = base.read_csv(GIRO)
    out: dict[tuple[str, str], dict] = {}

    for row in rows:
        action = str(row.get("AZIONE") or "")
        if "VAI IN ZONA" not in action.upper():
            continue
        town = str(row.get("COMUNE") or "").strip()
        if norm(town) not in town_rank:
            continue
        address = str(row.get("DOVE_ANDRE") or "").strip()
        street, civic = street_and_civic(address)
        if not street:
            continue
        key = (norm(town), norm(street))
        item = {
            "COMUNE": town,
            "INDIRIZZO": address,
            "VIA": street,
            "CIVICO": civic,
            "SCORE": score_value(row),
            "TIPO_OPPORTUNITA": str(row.get("TIPO_OPPORTUNITA") or row.get("SELLER_SIGNAL") or ""),
            "URL": str(row.get("URL") or ""),
            "COSA_CERCO": str(row.get("COSA_CERCO") or ""),
        }
        current = out.get(key)
        if current is None or item["SCORE"] > current["SCORE"]:
            out[key] = item
        elif civic and not current.get("CIVICO"):
            current["CIVICO"] = civic
            current["INDIRIZZO"] = address

    ordered = sorted(
        out.values(),
        key=lambda r: (town_rank.get(norm(r["COMUNE"]), 999), -r["SCORE"], norm(r["VIA"]))
    )
    return ordered[:MAX_STREETS]


def queries(stop: dict) -> list[str]:
    town, street, civic = stop["COMUNE"], stop["VIA"], stop.get("CIVICO") or ""
    q = []
    if civic:
        q.append(f'"{street} {civic}" "{town}" (telefono OR email OR contatti)')
    q.append(f'"{street}" "{town}" (telefono OR email OR contatti)')
    q.append(
        f'"{street}" "{town}" '
        '(impresa OR studio OR negozio OR bar OR ristorante OR pizzeria OR hotel OR officina '
        'OR parrucchiere OR estetista OR geometra OR architetto OR commercialista '
        'OR notaio OR amministratore OR condominio)'
    )
    return q


def page_matches_stop(text: str, stop: dict) -> tuple[bool, str]:
    hay = norm(text)
    town = norm(stop["COMUNE"])
    street = norm(stop["VIA"])
    if not town or not street or town not in hay or street not in hay:
        return False, ""
    civic = norm(stop.get("CIVICO") or "")
    if civic:
        if re.search(rf"(?:^| ){re.escape(civic)}(?: |$)", hay):
            return True, "CIVICO ESATTO"
    return True, "STESSA VIA"


def business_relevant(text: str) -> bool:
    low = str(text or "").casefold()
    if any(x in low for x in base.PUBLIC_ADMIN_WORDS):
        return False
    return any(x in low for x in base.BUSINESS_WORDS)


def key_for(row: dict) -> str:
    phone = base.normalize_phone(str(row.get("TELEFONO") or ""))
    email = str(row.get("EMAIL") or "").casefold().strip()
    if phone:
        return "p:" + phone
    if email:
        return "e:" + email
    return ""


def merge_existing(existing: list[dict], additions: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    loose: list[dict] = []

    for row in existing + additions:
        key = key_for(row)
        if not key:
            loose.append(row)
            continue
        if key not in merged:
            merged[key] = dict(row)
            continue
        cur = merged[key]
        if score_value(row) > score_value(cur):
            keep, other = dict(row), cur
        else:
            keep, other = cur, row
        if not keep.get("EMAIL") and other.get("EMAIL"):
            keep["EMAIL"] = other["EMAIL"]
        if not keep.get("TELEFONO") and other.get("TELEFONO"):
            keep["TELEFONO"] = other["TELEFONO"]
        if "GIRO_VIA" in str(row.get("CATEGORIA") or ""):
            keep["CATEGORIA"] = row["CATEGORIA"]
            keep["MOTIVO_CONTATTO"] = row.get("MOTIVO_CONTATTO") or keep.get("MOTIVO_CONTATTO", "")
            keep["RADAR_URL"] = row.get("RADAR_URL") or keep.get("RADAR_URL", "")
            keep["SEGNALE_RADAR"] = row.get("SEGNALE_RADAR") or keep.get("SEGNALE_RADAR", "")
            keep["RADAR_SCORE"] = row.get("RADAR_SCORE") or keep.get("RADAR_SCORE", "")
        merged[key] = keep

    rows = list(merged.values()) + loose
    rows.sort(key=lambda r: (-score_value(r), norm(r.get("COMUNE", "")), norm(r.get("NOME", ""))))
    return rows


def main() -> int:
    if not GIRO.exists():
        raise SystemExit(f"Giro acquisizione non trovato: {GIRO}")

    stops = route_stops()
    existing = base.read_csv(OUT)
    additions: list[dict] = []
    seen_sources: set[tuple[str, str]] = set()

    log(f"fermate via/civico da Giro: {len(stops)}")
    for pos, stop in enumerate(stops, 1):
        pages = 0
        found_here = 0
        for query in queries(stop):
            results, err = base.search(query, MAX_RESULTS)
            if err:
                log(f"{stop['COMUNE']} | {stop['VIA']}: {err}")
            for result in results:
                if pages >= MAX_PAGES_PER_STREET:
                    break
                url = base.safe_url(result.get("url") or "")
                if not url or (norm(stop["VIA"]), url) in seen_sources:
                    continue
                seen_sources.add((norm(stop["VIA"]), url))
                blob = " ".join([result.get("title") or "", result.get("snippet") or ""])
                if any(x in blob.casefold() for x in base.PUBLIC_ADMIN_WORDS):
                    continue
                body = base.fetch_html(url)
                if not body:
                    continue
                pages += 1
                combined = base.clean_text(body[:450000]) + " " + blob
                matched, match_type = page_matches_stop(combined, stop)
                if not matched or not business_relevant(combined):
                    continue

                phones, emails = base.extract_contacts(body)
                if not phones and not emails:
                    cpage = base.contact_page(url, body)
                    if cpage:
                        cbody = base.fetch_html(cpage)
                        if cbody:
                            combined2 = base.clean_text(cbody[:300000]) + " " + combined
                            matched2, match_type2 = page_matches_stop(combined2, stop)
                            if matched2 and business_relevant(combined2):
                                phones, emails = base.extract_contacts(cbody)
                                if phones or emails:
                                    url = cpage
                                    match_type = match_type2
                if not phones and not emails:
                    continue

                cat = base.category(combined)
                phone = phones[0] if phones else ""
                email = emails[0] if emails else ""
                score = 100 if match_type == "CIVICO ESATTO" else 92
                score = min(100, score + (4 if phone else 0))
                pid = hashlib.sha256(
                    f"route|{stop['COMUNE']}|{stop['VIA']}|{phone}|{email}|{url}".encode("utf-8")
                ).hexdigest()[:20]
                additions.append({
                    "PROSPECT_ID": pid,
                    "SCORE": score,
                    "COMUNE": stop["COMUNE"],
                    "NOME": (result.get("title") or urllib.parse.urlparse(url).netloc)[:180],
                    "CATEGORIA": "GIRO_VIA_" + cat,
                    "TELEFONO": phone,
                    "EMAIL": email,
                    "ALTRI_CONTATTI": " | ".join(phones[1:] + emails[1:]),
                    "MOTIVO_CONTATTO": (
                        f"Giro Seller Radar: {stop['COMUNE']} — {stop['INDIRIZZO']}. "
                        f"Contatto pubblico di attività/professionista trovato sulla stessa via "
                        f"({match_type}). Verificare fonte, pertinenza e RPO prima del contatto."
                    ),
                    "SEGNALE_RADAR": stop["TIPO_OPPORTUNITA"],
                    "RADAR_SCORE": stop["SCORE"],
                    "RADAR_URL": stop["URL"],
                    "FONTE_CONTATTO": urllib.parse.urlparse(url).netloc,
                    "URL_CONTATTO": url,
                    "PUBBLICO": "SI",
                    "RPO_STATUS": "DA_VERIFICARE_PRIMA_DEL_CONTATTO",
                    "STATO": "DA_CONTATTARE",
                })
                found_here += 1
        log(
            f"[{pos}/{len(stops)}] {stop['COMUNE']} | {stop['INDIRIZZO']} | "
            f"contatti via={found_here}"
        )

    rows = merge_existing(existing, additions)
    DATA.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    log(f"OK: +{len(additions)} contatti legati alle vie del Giro; totale prospect={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
