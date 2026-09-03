#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INPUT = DATA / "seller_master_660.csv"
OUT_JSON = DATA / "seller_master_660_analisi.json"
OUT_SUMMARY_CSV = DATA / "seller_master_660_tipologie.csv"
OUT_CLASSIFIED = DATA / "seller_master_660_classificato.csv"
EXPECTED_TOTAL = 660


def norm(value: object) -> str:
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def looks_like_search_or_category(row: dict) -> bool:
    title = norm(row.get("TITOLO"))
    url = norm(row.get("URL"))
    patterns = [
        r"\b\d+[\s\.]*(immobili|case|appartamenti|ville|rustici|capannoni|locali)\b",
        r"\b(case e appartamenti|immobili) a .+ (vendita|affitto)\b",
        r"\bimmobili in vendita a\b",
        r"\bcase in vendita a\b",
        r"\bappartamenti in vendita a\b",
        r"\bville in vendita a\b",
        r"\brustici in vendita a\b",
        r"\bmonolocali in vendita\b",
        r"\bcerca case\b",
        r"\bcerco casa portale\b",
        r"\bannunci case e appartamenti\b",
    ]
    if any(re.search(p, title) for p in patterns):
        return True
    # Pagine indice tipiche degli aggregatori, senza ID immobile specifico.
    if any(domain in url for domain in ("nestoria it immobiliare vendita", "case trovit it")) and not re.search(r"\bannunci?\b|\bimmobile\b\s*\d+", url):
        if not re.search(r"\bvia\b|\bborgata\b|\bfrazione\b|\bpiazza\b|\bcorso\b|\bstrada\b", title):
            return True
    return False


def looks_like_agency_or_service_page(row: dict) -> bool:
    title = norm(row.get("TITOLO"))
    source = norm(row.get("FONTE"))
    patterns = [
        r"\bagenzia immobiliare\b",
        r"\bstudio immobiliare\b",
        r"\bimmobiliare .+ agenzia\b",
        r"\bre max italia\b",
        r"\bgabetti\b",
        r"\btecnocasa\b",
        r"\btecnorete\b",
        r"\btempocasa\b",
        r"\bcoworking\b",
    ]
    # Se il titolo contiene chiaramente un singolo immobile, resta un annuncio immobile.
    single_property = bool(re.search(
        r"\b(appartamento|bilocale|trilocale|quadrilocale|villa|villetta|casa indipendente|terratetto|rustico|casale|baita|chalet|capannone|magazzino|negozio|locale commerciale|ufficio|terreno|box|garage)\b",
        title,
    ))
    return ("agenzie" in source or any(re.search(p, title) for p in patterns)) and not single_property


def infer_property_type(row: dict) -> str:
    text = norm(" ".join([row.get("TITOLO", ""), row.get("COSA_CERCO", ""), row.get("DOVE_ANDRE", "")]))
    rules = [
        ("GARAGE_BOX", [r"\bbox\b", r"\bgarage\b", r"autorimessa"]),
        ("TERRENO", [r"\bterreno\b", r"area edificabile", r"lotto edificabile"]),
        ("CAPANNONE_MAGAZZINO", [r"\bcapannone\b", r"\bmagazzino\b", r"\bdeposito\b", r"laboratorio industriale"]),
        ("NEGOZIO_COMMERCIALE", [r"\bnegozio\b", r"locale commerciale", r"attivita commerciale"]),
        ("UFFICIO", [r"\bufficio\b", r"studio professionale", r"direzionale"]),
        ("RUSTICO_CASALE_BAITA", [r"\brustico\b", r"\bcasale\b", r"\bcascina\b", r"casa colonica", r"\bbaita\b", r"\bchalet\b"]),
        ("VILLA", [r"\bvilla\b", r"\bvilletta\b"]),
        ("CASA_INDIPENDENTE_TERRATETTO", [r"casa indipendente", r"casa semindipendente", r"casa singola", r"porzione di casa", r"\bterratetto\b", r"\bterracielo\b"]),
        ("APPARTAMENTO", [r"\bappartamento\b", r"\bmansarda\b", r"\bmonolocale\b", r"\bbilocale\b", r"\btrilocale\b", r"\bquadrilocale\b", r"\bpentalocale\b"]),
        ("PALAZZO_EDIFICIO", [r"\bpalazzo\b", r"\bedificio\b", r"\bstabile\b"]),
    ]
    for label, patterns in rules:
        if any(re.search(p, text) for p in patterns):
            return label
    return "NON_DETERMINATO"


def classify_content(row: dict) -> str:
    if looks_like_search_or_category(row):
        return "PAGINA_RICERCA_CATEGORIA"
    if looks_like_agency_or_service_page(row):
        return "PAGINA_AGENZIA_SERVIZIO"
    subtype = infer_property_type(row)
    if subtype != "NON_DETERMINATO":
        return subtype
    return "ALTRO_NON_DETERMINATO"


def is_auction(row: dict) -> bool:
    text = norm(" ".join([row.get("TITOLO", ""), row.get("FONTE", ""), row.get("URL", "")]))
    return bool(re.search(r"\basta\b|\ball asta\b|astalegale|immobiliallasta", text))


def address_state(row: dict) -> str:
    address = str(row.get("DOVE_ANDRE") or "").strip()
    if not address or "INDIRIZZO DA VERIFICARE" in address.upper():
        return "DA_VERIFICARE"
    if re.search(r"\b\d+[A-Za-z]?(?:[/.-][A-Za-z0-9]+)?\b", address):
        return "CON_CIVICO"
    return "SENZA_CIVICO"


def duplicate_key(row: dict, content_type: str) -> str:
    comune = norm(row.get("COMUNE"))
    address = norm(row.get("DOVE_ANDRE"))
    title = norm(row.get("TITOLO"))
    if content_type in {"PAGINA_RICERCA_CATEGORIA", "PAGINA_AGENZIA_SERVIZIO", "ALTRO_NON_DETERMINATO"}:
        return ""
    if address and re.search(r"\b\d+[a-z]?\b", address):
        return f"{comune}|{address}|{content_type}"
    return f"{comune}|{title}|{content_type}"


def pct(n: int, total: int) -> float:
    return round(n * 100.0 / total, 1) if total else 0.0


def main() -> int:
    if not INPUT.exists():
        raise SystemExit(f"File mancante: {INPUT}")

    with INPUT.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if len(rows) != EXPECTED_TOTAL:
        raise SystemExit(f"FAIL MASTER 660: attese {EXPECTED_TOTAL} righe, trovate {len(rows)}")

    content_counts = Counter()
    software_counts = Counter()
    signal_counts = Counter()
    market_counts = Counter()
    address_counts = Counter()
    source_counts = Counter()
    comune_counts = Counter()
    duplicate_keys = Counter()
    auction_count = 0
    classified_rows = []

    for idx, row in enumerate(rows, start=1):
        content_type = classify_content(row)
        signal = (row.get("SELLER_SIGNAL") or "NON_DETERMINATO").strip() or "NON_DETERMINATO"
        software = (row.get("TIPO_OPPORTUNITA") or "NON_DETERMINATO").strip() or "NON_DETERMINATO"
        market = (row.get("STATO_MERCATO") or "NON_DETERMINATO").strip() or "NON_DETERMINATO"
        addr = address_state(row)
        auction = is_auction(row)

        content_counts[content_type] += 1
        software_counts[software] += 1
        signal_counts[signal] += 1
        market_counts[market] += 1
        address_counts[addr] += 1
        source_counts[(row.get("FONTE") or "NON_DETERMINATO").strip() or "NON_DETERMINATO"] += 1
        comune_counts[(row.get("COMUNE") or "NON_DETERMINATO").strip() or "NON_DETERMINATO"] += 1
        auction_count += int(auction)

        key = duplicate_key(row, content_type)
        if key:
            duplicate_keys[key] += 1

        out = dict(row)
        out["MASTER_660_ID"] = idx
        out["TIPOLOGIA_REALE_INFERITA"] = content_type
        out["ASTA_RILEVATA"] = "SI" if auction else "NO"
        out["STATO_INDIRIZZO_MASTER"] = addr
        out["MASTER_PRESERVATO"] = "SI"
        classified_rows.append(out)

    dup_groups = {k: n for k, n in duplicate_keys.items() if n > 1}
    dup_excess = sum(n - 1 for n in dup_groups.values())

    content_summary = [
        {"tipologia": k, "righe": v, "percentuale": pct(v, EXPECTED_TOTAL)}
        for k, v in content_counts.most_common()
    ]

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot_commit": "d56abc5b5b71bbd9aafbbd9cd0874722e14c8701",
        "source": str(INPUT.relative_to(ROOT)),
        "seller_totali_richiesti": EXPECTED_TOTAL,
        "seller_totali_analizzati": len(rows),
        "righe_preservate": len(classified_rows),
        "controllo_integrita": "PASS_660_SU_660" if len(classified_rows) == EXPECTED_TOTAL else "FAIL",
        "aste_rilevate": auction_count,
        "gruppi_duplicati_conservativi": len(dup_groups),
        "righe_duplicate_eccedenti_stimate": dup_excess,
        "per_tipologia_reale_inferita": content_summary,
        "per_tipologia_software": [
            {"tipologia_software": k, "righe": v, "percentuale": pct(v, EXPECTED_TOTAL)}
            for k, v in software_counts.most_common()
        ],
        "per_seller_signal": [
            {"seller_signal": k, "righe": v, "percentuale": pct(v, EXPECTED_TOTAL)}
            for k, v in signal_counts.most_common()
        ],
        "per_stato_mercato": [
            {"stato_mercato": k, "righe": v, "percentuale": pct(v, EXPECTED_TOTAL)}
            for k, v in market_counts.most_common()
        ],
        "per_stato_indirizzo": [
            {"stato_indirizzo": k, "righe": v, "percentuale": pct(v, EXPECTED_TOTAL)}
            for k, v in address_counts.most_common()
        ],
        "top_fonti": [{"fonte": k, "righe": v} for k, v in source_counts.most_common(30)],
        "per_comune": [{"comune": k, "righe": v} for k, v in comune_counts.most_common()],
    }

    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    with OUT_SUMMARY_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["tipologia", "righe", "percentuale"])
        w.writeheader()
        w.writerows(content_summary)

    fieldnames = list(rows[0].keys()) + ["MASTER_660_ID", "TIPOLOGIA_REALE_INFERITA", "ASTA_RILEVATA", "STATO_INDIRIZZO_MASTER", "MASTER_PRESERVATO"]
    with OUT_CLASSIFIED.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(classified_rows)

    print(f"PASS MASTER 660: analizzate={len(rows)} preservate={len(classified_rows)}")
    print(f"Aste={auction_count} duplicati_eccedenti_stimati={dup_excess}")
    for item in content_summary:
        print(f"- {item['tipologia']}: {item['righe']} ({item['percentuale']}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
