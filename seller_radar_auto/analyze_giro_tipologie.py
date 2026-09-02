#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INPUT = DATA / "giro_acquisizione_oggi.csv"
OUT_JSON = DATA / "giro_analisi_tipologie.json"
OUT_CSV = DATA / "giro_analisi_tipologie.csv"


def norm(value: object) -> str:
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def infer_subtype(row: dict) -> str:
    text = norm(" ".join([
        row.get("COSA_CERCO", ""),
        row.get("DOVE_ANDRE", ""),
        row.get("OBIETTIVO_COMMERCIALE", ""),
    ]))

    rules = [
        ("GARAGE_BOX", [r"\bbox\b", r"\bgarage\b", r"autorimessa"]),
        ("TERRENO", [r"\bterreno\b", r"area edificabile", r"lotto edificabile"]),
        ("CAPANNONE_MAGAZZINO", [r"\bcapannone\b", r"\bmagazzino\b", r"\bdeposito\b", r"laboratorio industriale"]),
        ("NEGOZIO_COMMERCIALE", [r"\bnegozio\b", r"locale commerciale", r"attivita commerciale"]),
        ("UFFICIO", [r"\bufficio\b", r"studio professionale", r"direzionale"]),
        ("RUSTICO_CASALE_BAITA", [r"\brustico\b", r"\bcasale\b", r"\bbaita\b", r"\bchalet\b"]),
        ("VILLA", [r"\bvilla\b", r"\bvilletta\b"]),
        ("CASA_INDIPENDENTE_TERRATETTO", [r"casa indipendente", r"\bterratetto\b", r"\bterracielo\b", r"casa singola"]),
        ("APPARTAMENTO", [r"\bappartamento\b", r"\bmonolocale\b", r"\bbilocale\b", r"\btrilocale\b", r"\bquadrilocale\b", r"\bpentalocale\b"]),
        ("PALAZZO_EDIFICIO", [r"\bpalazzo\b", r"\bedificio\b", r"\bstabile\b"]),
    ]
    for label, patterns in rules:
        if any(re.search(p, text) for p in patterns):
            return label
    return "ALTRO_NON_DETERMINATO"


EXPECTED_SYSTEM = {
    "APPARTAMENTO": "RESIDENZIALE",
    "VILLA": "RESIDENZIALE",
    "CASA_INDIPENDENTE_TERRATETTO": "RESIDENZIALE",
    "RUSTICO_CASALE_BAITA": "RESIDENZIALE",
    "CAPANNONE_MAGAZZINO": "INDUSTRIALE_LOGISTICA",
    "NEGOZIO_COMMERCIALE": "COMMERCIALE_IMMOBILE",
    "UFFICIO": "UFFICIO_DIREZIONALE",
}


def conservative_property_key(row: dict, subtype: str) -> str:
    comune = norm(row.get("COMUNE"))
    addr = norm(row.get("DOVE_ANDRE"))
    title = norm(row.get("COSA_CERCO"))
    # Solo gli indirizzi con numero civico sono usati per deduplica cross-portale.
    # Se manca il civico, usiamo il titolo per non fondere immobili diversi sulla stessa via.
    if addr and re.search(r"\b\d+[a-z]?\b", addr):
        return f"{comune}|{addr}|{subtype}"
    return f"{comune}|{title}|{subtype}"


def pct(n: int, total: int) -> float:
    return round((n * 100.0 / total), 1) if total else 0.0


def main() -> int:
    if not INPUT.exists():
        raise SystemExit(f"File mancante: {INPUT}")

    with INPUT.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    system = defaultdict(lambda: Counter())
    subtype = defaultdict(lambda: Counter())
    unique_keys = defaultdict(set)
    all_keys = []
    mismatches = []
    auction_rows = 0
    private_signal_rows = 0

    for row in rows:
        sys_type = (row.get("TIPO_OPPORTUNITA") or "NON_DETERMINATO").strip() or "NON_DETERMINATO"
        sub = infer_subtype(row)
        giro = (row.get("STATO_GIRO") or "").strip()
        assignment = (row.get("STATO_ASSEGNAZIONE") or "").strip()
        seller_signal = (row.get("SELLER_SIGNAL") or "").strip()

        system[sys_type]["righe"] += 1
        system[sys_type][giro or "STATO_GIRO_VUOTO"] += 1
        if assignment == "ASSEGNATO":
            system[sys_type]["assegnate"] += 1

        subtype[sub]["righe"] += 1
        subtype[sub][giro or "STATO_GIRO_VUOTO"] += 1
        if assignment == "ASSEGNATO":
            subtype[sub]["assegnate"] += 1

        key = conservative_property_key(row, sub)
        unique_keys[sub].add(key)
        all_keys.append(key)

        text = norm(" ".join([row.get("COSA_CERCO", ""), row.get("FONTE", "")]))
        if " asta " in f" {text} " or "all asta" in text or "astalegale" in text or "immobiliallasta" in text:
            auction_rows += 1
        if seller_signal == "INDIZIO_PRIVATO":
            private_signal_rows += 1

        expected = EXPECTED_SYSTEM.get(sub)
        if expected and sys_type != expected:
            mismatches.append({
                "comune": row.get("COMUNE", ""),
                "indirizzo": row.get("DOVE_ANDRE", ""),
                "titolo": row.get("COSA_CERCO", ""),
                "tipo_software": sys_type,
                "tipo_reale_inferito": sub,
                "tipo_atteso": expected,
                "fonte": row.get("FONTE", ""),
                "url": row.get("URL", ""),
            })

    system_rows = []
    for label, c in sorted(system.items(), key=lambda kv: (-kv[1]["righe"], kv[0])):
        system_rows.append({
            "tipologia_software": label,
            "righe": c["righe"],
            "percentuale": pct(c["righe"], total),
            "fermate_pronte": c["FERMATA_PRONTA"],
            "da_verificare": c["DA_VERIFICARE"],
            "assegnate": c["assegnate"],
        })

    subtype_rows = []
    for label, c in sorted(subtype.items(), key=lambda kv: (-kv[1]["righe"], kv[0])):
        subtype_rows.append({
            "tipologia_reale_inferita": label,
            "righe": c["righe"],
            "percentuale": pct(c["righe"], total),
            "immobili_unici_stimati": len(unique_keys[label]),
            "fermate_pronte": c["FERMATA_PRONTA"],
            "da_verificare": c["DA_VERIFICARE"],
            "assegnate": c["assegnate"],
        })

    key_counts = Counter(all_keys)
    duplicate_groups = {k: n for k, n in key_counts.items() if n > 1}
    duplicate_rows_excess = sum(n - 1 for n in duplicate_groups.values())

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(INPUT.relative_to(ROOT)),
        "totale_righe_giro_oggi": total,
        "immobili_unici_stimati": total - duplicate_rows_excess,
        "gruppi_duplicati_conservativi": len(duplicate_groups),
        "righe_duplicate_eccedenti_stimate": duplicate_rows_excess,
        "aste_rilevate": auction_rows,
        "indizi_privato": private_signal_rows,
        "classificazioni_sospette": len(mismatches),
        "per_tipologia_software": system_rows,
        "per_tipologia_reale_inferita": subtype_rows,
        "esempi_classificazione_sospetta": mismatches[:40],
    }

    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "tipologia_reale_inferita", "righe", "percentuale", "immobili_unici_stimati",
            "fermate_pronte", "da_verificare", "assegnate"
        ])
        w.writeheader()
        w.writerows(subtype_rows)

    print(
        f"ANALISI TIPOLOGIE: righe={total}; unici_stimati={total - duplicate_rows_excess}; "
        f"duplicati_eccedenti={duplicate_rows_excess}; aste={auction_rows}; "
        f"indizi_privato={private_signal_rows}; classificazioni_sospette={len(mismatches)}"
    )
    for r in subtype_rows:
        print(f"- {r['tipologia_reale_inferita']}: {r['righe']} righe / {r['immobili_unici_stimati']} unici stimati")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
