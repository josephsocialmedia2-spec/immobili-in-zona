from __future__ import annotations

"""Compatibilita legacy F1 Seller Radar.

Questo modulo NON esegue piu ricerche autonome. Il motore ufficiale e unico e:
    seller_radar_auto/

Se questo vecchio script viene lanciato, copia semplicemente l'ultimo output
operativo ufficiale nel vecchio percorso report.csv per non rompere eventuali
collegamenti locali. Nessuna seconda pipeline, nessun secondo scoring.
"""

import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
CANONICAL = ROOT / "seller_radar_auto" / "data" / "giro_acquisizione.csv"
REPORT_CSV = BASE / "report.csv"
REPORT_HTML = BASE / "report.html"

REDIRECT_HTML = """<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta http-equiv='refresh' content='0; url=https://josephsocialmedia2-spec.github.io/launcher-dashboard/oggi.html'><title>F1 Seller Radar centralizzato</title></head><body><p>F1 Seller Radar e stato centralizzato in <a href='https://josephsocialmedia2-spec.github.io/launcher-dashboard/oggi.html'>OGGI COSA FACCIO</a>.</p></body></html>"""


def main() -> None:
    if not CANONICAL.exists():
        raise SystemExit(
            "Output ufficiale non disponibile. Esegui F1 Seller Radar AUTO; "
            "questo modulo legacy non effettua piu ricerche autonome."
        )
    shutil.copyfile(CANONICAL, REPORT_CSV)
    REPORT_HTML.write_text(REDIRECT_HTML, encoding="utf-8")
    print(
        "LEGACY SELLER RADAR: nessuna ricerca autonoma. "
        f"Mirror aggiornato da {CANONICAL}. Usa OGGI COSA FACCIO."
    )


if __name__ == "__main__":
    main()
