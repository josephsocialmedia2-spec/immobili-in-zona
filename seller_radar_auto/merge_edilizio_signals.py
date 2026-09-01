#!/usr/bin/env python3
import csv
import io
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
GIRO = DATA / "giro_acquisizione.csv"
OUT = DATA / "edilizio_seller_signals.csv"
RADAR_URL = "https://josephsocialmedia2-spec.github.io/launcher-dashboard/data/radar_edilizio.json"


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def fetch_db():
    req = urllib.request.Request(RADAR_URL, headers={"User-Agent": "F1-Seller-Radar-Edilizio/1.1"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def practice_id(comune, atto):
    town = norm(comune)
    text = norm(atto)
    # Identificatore stabile per evitare che la stessa pratica compaia sia
    # come opportunità qualificata sia come backlog.
    patterns = [
        r"\balbo\s*(\d+\s*/\s*\d{4})",
        r"\bpdc(?:\s+in\s+sanatoria)?\s*(\d+\s*/\s*\d{4})",
        r"\bscia(?:\s+alternativa(?:\s+a\s+pdc)?)?\s*(\d+\s*/\s*\d{4})",
        r"\bscagi\s*(\d+\s*/\s*\d{4})",
        r"\b(?:accertamento\s+conformit[aà])\s*(\d+\s*/\s*\d{4})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            number = re.sub(r"\s+", "", m.group(1))
            label = pattern.split("\\b")[1].split("(")[0].replace("\\s+", "_").replace("?:", "")[:20]
            return f"{town}|{label}|{number}"
    return f"{town}|{text}"


def contact_index(db):
    out = []
    for c in db.get("contacts", []):
        out.append({
            "pratica": norm(c.get("pratica")),
            "nome": str(c.get("nome") or "").strip(),
            "ruolo": str(c.get("ruolo") or "").strip(),
            "telefono": str(c.get("telefono") or "").strip(),
            "email": str(c.get("email") or "").strip(),
            "stato": str(c.get("stato") or "").strip(),
        })
    return out


def find_contact(atto, contacts):
    a = norm(atto)
    if not a:
        return None
    for c in contacts:
        p = c["pratica"]
        if p and (p in a or a in p):
            return c
    return None


def ref_text(contact):
    if not contact:
        return ""
    bits = [contact.get("ruolo"), contact.get("nome")]
    if contact.get("telefono"):
        bits.append("TEL " + contact["telefono"])
    if contact.get("email"):
        bits.append("EMAIL " + contact["email"])
    return " · ".join(x for x in bits if x)


def score(priority, verified=True):
    p = str(priority or "MEDIA").upper()
    base = {"ALTA": 95, "MEDIA": 75, "BASSA": 55}.get(p, 65)
    return base if verified else max(45, base - 10)


def target_for(text):
    t = norm(text)
    if "terreno" in t or "lotto" in t:
        return "TERRENO"
    if "residen" in t or "abit" in t or "destinazione d'uso" in t:
        return "IMMOBILE"
    return "PROFESSIONISTA / CANTIERE"


def row_from_opportunity(o, headers, contacts):
    c = find_contact(o.get("atto"), contacts)
    ref = ref_text(c)
    priority = str(o.get("priorita") or "MEDIA").upper()
    address = str(o.get("indirizzo") or "DA APPROFONDIRE").strip()
    description = " · ".join(x for x in [o.get("tipo"), o.get("descrizione"), ref] if x)
    action = str(o.get("azione") or "APRI FONTE E QUALIFICA").strip()
    if ref:
        action += " · RIFERIMENTO: " + ref
    row = {h: "" for h in headers}
    row.update({
        "STATO_ASSEGNAZIONE": "DA_ASSEGNARE",
        "TERRITORIO_OPERATIVO": "SI",
        "STATO_GIRO": "DA_VERIFICARE" if "approfondire" in norm(address) else "FERMATA_PRONTA",
        "STATO_MERCATO": "NEW",
        "PRIORITA": priority,
        "SCORE": str(score(priority, bool(o.get("verified")))),
        "TIPO_OPPORTUNITA": "EDILIZIO_" + re.sub(r"[^A-Z0-9]+", "_", str(o.get("tipo") or "OPPORTUNITA").upper()).strip("_")[:45],
        "TARGET": target_for(description),
        "FASE_PROGETTO": str(o.get("atto") or "").strip(),
        "OBIETTIVO_COMMERCIALE": "ACQUISIZIONE / NETWORKING TERRITORIALE",
        "COMUNE": str(o.get("comune") or "").strip(),
        "DOVE_ANDRE": address,
        "COSA_CERCO": description,
        "PREZZO": "NON APPLICABILE",
        "FONTE": "RADAR EDILIZIO F1",
        "SELLER_SIGNAL": "RADAR_EDILIZIO",
        "AZIONE": action,
        "URL": str(o.get("source_url") or "").strip(),
    })
    return row


def row_from_backlog(b, headers):
    atto = str(b.get("atto") or "Atto edilizio").strip()
    classe = str(b.get("classe") or "Atto edilizio").strip()
    row = {h: "" for h in headers}
    row.update({
        "STATO_ASSEGNAZIONE": "DA_ASSEGNARE",
        "TERRITORIO_OPERATIVO": "SI",
        "STATO_GIRO": "DA_VERIFICARE",
        "STATO_MERCATO": "NEW",
        "PRIORITA": "MEDIA",
        "SCORE": "65",
        "TIPO_OPPORTUNITA": "EDILIZIO_DA_APPROFONDIRE",
        "TARGET": target_for(classe + " " + atto),
        "FASE_PROGETTO": atto,
        "OBIETTIVO_COMMERCIALE": "QUALIFICA OPPORTUNITA / CERCA TECNICO O IMPRESA",
        "COMUNE": str(b.get("comune") or "").strip(),
        "DOVE_ANDRE": "INDIRIZZO DA VERIFICARE",
        "COSA_CERCO": f"{classe} · {atto} · verifica indirizzo, progettista, impresa e potenziale acquisizione",
        "PREZZO": "NON APPLICABILE",
        "FONTE": "RADAR EDILIZIO F1 - BACKLOG",
        "SELLER_SIGNAL": "RADAR_EDILIZIO_BACKLOG",
        "AZIONE": "APRI FONTE → TROVA INDIRIZZO → TROVA TECNICO/IMPRESA → QUALIFICA PER ACQUISIZIONE",
        "URL": str(b.get("source_url") or "").strip(),
    })
    return row


def main():
    if not GIRO.exists():
        raise SystemExit(f"File Seller Radar mancante: {GIRO}")

    db = fetch_db()
    with GIRO.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        existing = list(reader)

    required = {"COMUNE", "DOVE_ANDRE", "COSA_CERCO", "FONTE", "SELLER_SIGNAL", "AZIONE", "URL"}
    missing = required.difference(headers)
    if missing:
        raise SystemExit("Schema giro_acquisizione incompatibile: " + ", ".join(sorted(missing)))

    contacts = contact_index(db)
    opportunities = list(db.get("opportunities", []))
    backlog = list(db.get("backlog", []))

    # Le opportunità qualificate hanno precedenza. Se la stessa pratica è nel
    # backlog, il backlog non genera una seconda riga.
    qualified_ids = {practice_id(o.get("comune"), o.get("atto")) for o in opportunities}
    candidates = [row_from_opportunity(o, headers, contacts) for o in opportunities]
    skipped_backlog = 0
    for b in backlog:
        if practice_id(b.get("comune"), b.get("atto")) in qualified_ids:
            skipped_backlog += 1
            continue
        candidates.append(row_from_backlog(b, headers))

    base = [r for r in existing if not str(r.get("SELLER_SIGNAL") or "").startswith("RADAR_EDILIZIO")]
    merged = list(base)
    added = []
    seen_practices = set()
    for row in candidates:
        if not row.get("COMUNE"):
            continue
        pid = practice_id(row.get("COMUNE"), row.get("FASE_PROGETTO"))
        if pid in seen_practices:
            continue
        seen_practices.add(pid)
        merged.append(row)
        added.append(row)

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(merged)
    GIRO.write_text("\ufeff" + buf.getvalue(), encoding="utf-8", newline="")

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(added)

    if not added:
        raise SystemExit("Nessun segnale edilizio generato: integrazione non valida")
    print(json.dumps({
        "qualified": len(opportunities),
        "backlog": len(backlog),
        "backlog_duplicates_skipped": skipped_backlog,
        "unique_edilizio_signals": len(added),
        "seller_rows_total": len(merged)
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
