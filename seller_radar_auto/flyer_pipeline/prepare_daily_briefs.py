from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "seller_radar_auto" / "data" / "work_queue.csv"
PIPELINE = ROOT / "seller_radar_auto" / "flyer_pipeline"
QUEUE_ROOT = PIPELINE / "queue"
READY_ROOT = PIPELINE / "ready"

ROME = ZoneInfo("Europe/Rome")
CONTACTS = {
    "joseph": "+39 371 370 8294",
    "francesca": "+39 371 424 6300",
    "email": "f1immobiliaresusa@outlook.it",
    "site": "https://f1immobiliare.com/",
}


def clean_street(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    # Elimina il civico finale e forme s.n.c./snc senza alterare il nome della via.
    value = re.sub(r"\s+(?:\d+[A-Za-z]?(?:[/\-]\d+[A-Za-z]?)?|s\.?n\.?c\.?)\s*$", "", value, flags=re.I)
    return value.strip(" ,-")


def number(value: str) -> float | None:
    if not value:
        return None
    text = re.sub(r"[^0-9,.-]", "", str(value)).replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def signal_for(row: dict[str, str]) -> tuple[str, str, str | None]:
    current = number(row.get("PREZZO", ""))
    previous = number(row.get("PREZZO_PRECEDENTE", ""))
    drops = int(number(row.get("RIBASSI", "")) or 0)
    reasons = (row.get("MOTIVI", "") or "").lower()
    advertiser = (row.get("INDIZIO_INSERZIONISTA", "") or "").lower()
    status = (row.get("STATO", "") or "").lower()

    if current and previous and previous > current:
        pct = round((previous - current) / previous * 100, 1)
        return "RIBASSO", "riduzione di prezzo", f"{pct:.1f}%".replace(".", ",")
    if drops >= 2:
        return "RIBASSI_MULTIPLI", "successive riduzioni di prezzo", None
    if "ribass" in reasons or drops == 1:
        return "RIBASSO", "riduzione di prezzo", None
    if "invend" in reasons or "lung" in reasons or "fermo" in reasons:
        return "INVENDUTO", "lunga permanenza sul mercato", None
    if "concorren" in reasons:
        return "CONCORRENZA", "forte concorrenza nella zona", None
    if "privat" in advertiser or "no agenz" in advertiser:
        return "PRIVATO", "vendita da privato", None
    if status == "new":
        return "NUOVO", "nuova pubblicazione", None
    return "MONITORAGGIO", "segnale di mercato", None


def public_copy(signal: str, pct: str | None) -> dict[str, str]:
    if signal == "RIBASSO":
        body = "Un prezzo iniziale non corretto può portare a ribassi, tempi di vendita più lunghi e perdita di forza nella trattativa."
        fact = f"Abbiamo rilevato nella zona un recente segnale di ribasso del {pct}." if pct else "Abbiamo rilevato nella zona un recente segnale di ribasso di prezzo."
    elif signal == "RIBASSI_MULTIPLI":
        body = "Correggere più volte il prezzo durante la vendita può indebolire il posizionamento dell'immobile."
        fact = "Abbiamo rilevato nella zona segnali di successive riduzioni di prezzo."
    elif signal == "INVENDUTO":
        body = "Restare troppo tempo sul mercato può ridurre l'interesse degli acquirenti e indebolire la percezione del valore dell'immobile."
        fact = "Abbiamo rilevato nella zona un recente segnale di lunga permanenza sul mercato."
    elif signal == "CONCORRENZA":
        body = "Quando molti immobili simili competono nella stessa zona, prezzo, presentazione e strategia diventano determinanti."
        fact = "Abbiamo rilevato una presenza significativa di immobili concorrenti nella zona."
    else:
        body = "Prima di mettere casa in vendita è utile verificare prezzo, concorrenza e corretto posizionamento sul mercato."
        fact = "Abbiamo rilevato nella zona un nuovo segnale di mercato immobiliare."

    return {
        "headline": "🏠 VUOI VENDERE CASA IN QUESTA ZONA?",
        "problem": body,
        "signal_line": fact,
        "bridge": "Prima di pubblicare il tuo immobile, scopri quale potrebbe essere il suo corretto posizionamento sul mercato.",
        "cta": "RICHIEDI UNA VALUTAZIONE GRATUITA",
    }


def slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-")
    return text or "zona"


def main() -> None:
    today = datetime.now(ROME).date().isoformat()
    out_dir = QUEUE_ROOT / today
    out_dir.mkdir(parents=True, exist_ok=True)
    (READY_ROOT / today).mkdir(parents=True, exist_ok=True)

    if not DATA.exists():
        print(f"Nessun work_queue trovato: {DATA}")
        return

    with DATA.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    briefs = []
    seen = set()
    for row in rows:
        comune = (row.get("COMUNE", "") or "").strip()
        via = clean_street(row.get("VIA_RADAR", ""))
        if not comune or not via:
            continue

        signal, commercial_problem, pct = signal_for(row)
        key = (comune.lower(), via.lower(), signal)
        if key in seen:
            continue
        seen.add(key)

        copy = public_copy(signal, pct)
        brief = {
            "date": today,
            "format": "A6 verticale 105x148 mm",
            "background": "bianco",
            "layout": {"top": "55-65% grande", "bottom": "35-45% piccolo"},
            "territory": {"comune": comune, "via": via, "public_label": f"{comune} – {via} e zona limitrofa"},
            "signal": {"type": signal, "commercial_problem": commercial_problem, "percentage": pct},
            "public_copy": copy,
            "small_copy": {
                "intro": "Con una prima analisi verifichiamo:",
                "bullets": [
                    "il possibile valore di mercato",
                    "gli immobili concorrenti attualmente in vendita",
                    "il corretto posizionamento del prezzo",
                    "eventuali criticità che potrebbero rallentare la vendita",
                    "la strategia per aumentare l'interesse sull'immobile",
                ],
                "goal": "L'obiettivo: partire con una strategia corretta, ridurre il rischio di successivi ribassi e creare le condizioni per vendere più efficacemente.",
                "brand": "F1 IMMOBILIARE — Strategia • Valutazione • Promozione Immobiliare",
                "cta": "Richiedi gratuitamente la tua prima analisi immobiliare.",
            },
            "contacts": CONTACTS,
            "assets_rule": "Usare esclusivamente logo/foto team/immagini F1 approvate; mai la foto dell'immobile segnalato.",
            "privacy_rule": "Mai civico, prezzo preciso, nome proprietario/inserzionista, link annuncio o altri dati identificativi nel volantino pubblico.",
            "source_internal": {
                "fonte": row.get("FONTE", ""),
                "titolo": row.get("TITOLO", ""),
                "url": row.get("URL", ""),
                "score": row.get("SCORE", ""),
                "priorita": row.get("PRIORITA", ""),
            },
        }
        filename = f"F1_SellerSignal_{slug(comune)}_{slug(via)}_{signal}_{today}.json"
        (out_dir / filename).write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
        briefs.append(filename)

    index = {
        "date": today,
        "generated_at": datetime.now(ROME).isoformat(),
        "count": len(briefs),
        "queue": briefs,
        "ready_folder": f"seller_radar_auto/flyer_pipeline/ready/{today}/",
        "prompt": "seller_radar_auto/flyer_pipeline/PROMPT_MASTER.md",
    }
    (out_dir / "INDEX.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(index, ensure_ascii=False))


if __name__ == "__main__":
    main()
