#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ordina LISTA_MATTINO mettendo Susa + raggio 10 km davanti a tutto.

Non cancella record e non pubblica dati: lavora esclusivamente sui file locali
prodotti dal bridge telefonate. Crea inoltre una vista focalizzata per iniziare
subito le chiamate nella zona prioritaria.
"""
from __future__ import annotations

import csv
import html
import re
import unicodedata
from pathlib import Path

BASE = Path.home() / "Documents" / "F1_Directory_Microzone"
DATA = BASE / "data"
FULL_HTML = BASE / "LISTA_MATTINO.html"
FOCUS_HTML = BASE / "LISTA_SUSA_10KM.html"
FULL_CSV = DATA / "telefonate_mattino.csv"
FOCUS_CSV = DATA / "telefonate_susa_10km.csv"
SUMMARY = BASE / "PRIORITA_SUSA_10KM.txt"

PRIORITY_TOWNS = [
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


def norm(value: str) -> str:
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s.casefold()).strip()
    aliases = {
        "san giorio": "san giorio di susa",
        "borgone susa": "borgone di susa",
    }
    return aliases.get(s, s)


PRIORITY_NORM = [norm(x) for x in PRIORITY_TOWNS]
PRIORITY_RANK = {name: i for i, name in enumerate(PRIORITY_NORM)}


def rank_town(value: str) -> int:
    return PRIORITY_RANK.get(norm(value), 999)


def is_priority(value: str) -> bool:
    return rank_town(value) < 999


def row_town(row: dict) -> str:
    for key in ("COMUNE", "RADAR_COMUNE", "Comune", "comune"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def sort_csv() -> tuple[int, int]:
    if not FULL_CSV.exists():
        return 0, 0
    with FULL_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    rows.sort(key=lambda r: (rank_town(row_town(r)), norm(row_town(r)), norm(r.get("VIA_TARGET", "")), norm(r.get("VIA_CONTATTO", "")), norm(r.get("CIVICO", ""))))
    with FULL_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    focus = [r for r in rows if is_priority(row_town(r))]
    with FOCUS_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(focus)
    return len(rows), len(focus)


def sort_html() -> tuple[int, int]:
    if not FULL_HTML.exists():
        return 0, 0
    text = FULL_HTML.read_text(encoding="utf-8")
    start_marker = "<div id='cards'>"
    end_marker = "</div><h2>OPPORTUNITÀ ASSEGNATE SENZA MICROZONA / NUMERI</h2>"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        return 0, 0
    content_start = start + len(start_marker)
    cards_blob = text[content_start:end]
    cards = re.findall(r"<section class='card'[^>]*>.*?</section>", cards_blob, flags=re.S)

    def town_from_card(card: str) -> str:
        match = re.search(r"<div class='town'>(.*?)</div>", card, flags=re.S)
        if not match:
            return ""
        return html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()

    cards.sort(key=lambda card: (rank_town(town_from_card(card)), norm(town_from_card(card))))
    priority_cards = [c for c in cards if is_priority(town_from_card(c))]
    banner = (
        "<div class='note'><b>PRIORITÀ OPERATIVA: SUSA + 10 KM.</b> "
        "Le schede di Susa e dei comuni nel raggio prioritario sono mostrate per prime. "
        "Gli altri territori restano sotto e non vengono cancellati.</div>"
    )
    full = text[:content_start] + banner + "".join(cards) + text[end:]
    FULL_HTML.write_text(full, encoding="utf-8")

    script_pos = text.rfind("<script>")
    if script_pos < 0:
        suffix = "</main></body></html>"
    else:
        suffix = text[script_pos:]
    focus_prefix = text[:content_start]
    focus_prefix = focus_prefix.replace("F1 — LISTA MATTINO COMPLETA", "F1 — SUSA + 10 KM — TELEFONATE", 1)
    focus_note = (
        "<div class='note'><b>VISTA OPERATIVA PRIORITARIA.</b> "
        "Qui sono mostrate solo le microzone di Susa e dei comuni entro circa 10 km. "
        "La LISTA_MATTINO completa resta disponibile e invariata nei contenuti.</div>"
    )
    focused = (
        focus_prefix + focus_note + "".join(priority_cards) + "</div>"
        + "<h2>AREA PRIORITARIA SUSA + 10 KM</h2>"
        + "<p class='muted'>Per le altre aree apri LISTA_MATTINO.html.</p>"
        + suffix
    )
    FOCUS_HTML.write_text(focused, encoding="utf-8")
    return len(cards), len(priority_cards)


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    all_csv, focus_csv = sort_csv()
    all_cards, focus_cards = sort_html()
    SUMMARY.write_text(
        "PRIORITA OPERATIVA F1 — SUSA + 10 KM\n"
        + "Comuni: " + ", ".join(PRIORITY_TOWNS) + "\n"
        + f"Righe telefonate totali: {all_csv}\n"
        + f"Righe telefonate Susa+10km: {focus_csv}\n"
        + f"Microzone totali: {all_cards}\n"
        + f"Microzone Susa+10km: {focus_cards}\n"
        + f"Vista prioritaria: {FOCUS_HTML}\n"
        + f"CSV prioritario: {FOCUS_CSV}\n",
        encoding="utf-8",
    )
    print(f"PRIORITA SUSA 10 KM: {focus_csv}/{all_csv} telefonate, {focus_cards}/{all_cards} microzone")
    print(f"APRI: {FOCUS_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
