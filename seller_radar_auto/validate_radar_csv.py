#!/usr/bin/env python3
"""
F1 Radar CSV quality gate.

Purpose:
- clean radar CSV output before it reaches the operative CRM;
- reject category/search pages and obvious non-property results;
- detect agency ads so they are not scored as private sellers;
- reject known false phone captures such as Subito's VAT number 05526340962;
- keep only phone values already present in the input CSV and validate their format.
This script does NOT scrape pages, bypass protections, or discover new personal contacts.
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

KNOWN_NOT_PHONES = {
    "05526340962",  # Subito.it P.IVA
    "5526340962",   # same value if leading zero was lost by spreadsheet conversion
}

AGENCY_TERMS = (
    "tecnocasa", "tecnorete", "tempocasa", "gabetti", "re/max", "remax",
    "immobiliare segusium", "studio sviluppo sas", "immobiliare bussolin sas",
    "industriale provincia torino ovest", "investo s.r.l", "investo srl",
)

IRRELEVANT_TERMS = (
    "moto e scooter", "moto usata", "scooter", "auto usata", "offerte di lavoro",
    "assistenza domiciliare", "il cuoco in casa", "libri e riviste",
    "servizi in vendita", "affitto vacanze",
)

OUTSIDE_AREA_TERMS = (
    "milano", "alessandria", "casaleggio boiro", "lanzo torinese",
)

def fold(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()

def digits(value: str) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    s = re.sub(r"\D", "", s)
    if s.startswith("0039"):
        s = s[4:]
    elif s.startswith("39") and len(s) in (11, 12):
        s = s[2:]
    return s

def is_valid_it_phone(value: str) -> bool:
    s = digits(value)
    if not s or s in KNOWN_NOT_PHONES:
        return False
    return bool(re.fullmatch(r"3\d{9}", s) or re.fullmatch(r"0\d{5,10}", s))

def is_detail_url(url: str) -> bool:
    return bool(re.search(r"https?://(?:www\.)?subito\.it/[^?#]+\.htm(?:$|[?#])", url or "", re.I))

def normalize_price(value: str, detail: bool) -> str:
    try:
        n = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if detail and n < 5000:
        n *= 1000
    return str(int(round(n)))

def clean_location(value: str) -> str:
    s = re.sub(r"\s+", " ", value or "").strip()
    s = re.sub(r"\b(?:per informazioni|info)\s+(?:contattare\s+)?(?:\+?39\s*)?\d[\d\s.-]{7,}\b.*$", "", s, flags=re.I)
    s = re.sub(r"\bnon voglio essere contattato\b.*$", "", s, flags=re.I)
    if len(s) > 100:
        return "CIVICO DA VERIFICARE"
    return s or "CIVICO DA VERIFICARE"

def classify(row: dict) -> tuple[str, str]:
    title = row.get("titolo", "")
    summary = row.get("sintesi", "")
    url = row.get("fonte_link", "")
    text = fold(f"{title} {summary}")

    if not is_detail_url(url):
        return "SCARTA", "PAGINA_CATEGORIA_O_RICERCA"
    if any(term in text for term in OUTSIDE_AREA_TERMS):
        return "SCARTA", "FUORI_TERRITORIO"
    if any(term in text for term in IRRELEVANT_TERMS):
        return "SCARTA", "RISULTATO_NON_OPERATIVO"
    if re.search(r"\basta\b", text):
        return "SCARTA", "ASTA"
    if any(term in text for term in AGENCY_TERMS):
        return "AGENZIA", "INSERZIONISTA_AGENZIA"
    return "CANDIDATO", ""

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_csv", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args()

    out = args.output or args.input_csv.with_name(args.input_csv.stem + "_PULITO.csv")

    with args.input_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)
        in_fields = reader.fieldnames or []

    phone_counts = Counter(digits(r.get("telefono_pubblico", "")) for r in rows)
    extra_fields = [
        "esito_qualita", "motivo_scarto", "prezzo_normalizzato_eur",
        "indirizzo_operativo", "telefono_validato", "telefono_stato",
    ]

    cleaned = []
    for row in rows:
        esito, motivo = classify(row)
        detail = is_detail_url(row.get("fonte_link", ""))
        phone = digits(row.get("telefono_pubblico", ""))

        if phone in KNOWN_NOT_PHONES:
            phone_status = "SCARTATO_PIVA_SUBITO"
            phone_out = ""
        elif phone and phone_counts[phone] >= 10:
            phone_status = "SOSPETTO_RIPETUTO"
            phone_out = ""
        elif is_valid_it_phone(phone):
            phone_status = "FORMATO_PLAUSIBILE_DA_VERIFICARE_SU_FONTE"
            phone_out = phone
        else:
            phone_status = "NON_DISPONIBILE" if not phone else "FORMATO_NON_VALIDO"
            phone_out = ""

        row["esito_qualita"] = esito
        row["motivo_scarto"] = motivo
        row["prezzo_normalizzato_eur"] = normalize_price(row.get("prezzo", ""), detail)
        row["indirizzo_operativo"] = clean_location(row.get("via_zona", ""))
        row["telefono_validato"] = phone_out
        row["telefono_stato"] = phone_status
        cleaned.append(row)

    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=in_fields + extra_fields, delimiter=";")
        writer.writeheader()
        writer.writerows(cleaned)

    counts = Counter(r["esito_qualita"] for r in cleaned)
    valid_phones = {r["telefono_validato"] for r in cleaned if r["telefono_validato"]}
    print(f"Righe totali: {len(cleaned)}")
    for k in ("CANDIDATO", "AGENZIA", "SCARTA"):
        print(f"{k}: {counts[k]}")
    print(f"Telefoni plausibili distinti gia presenti nel CSV: {len(valid_phones)}")
    print(f"Output: {out}")

if __name__ == "__main__":
    main()
