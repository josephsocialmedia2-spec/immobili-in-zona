#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "intelligence"
CONFIG = ROOT / "cross_repo_sources.json"
OUT_RECORDS = DATA / "external_records.csv"
OUT_STATUS = DATA / "repo_status.csv"
OUT_SUMMARY = DATA / "repo_status.json"

ALIASES = {
    "comune": ["comune", "COMUNE", "paese", "PAESE", "municipality"],
    "via": ["via", "VIA", "via_zona", "VIA_RADAR", "DOVE_ANDRE", "DOVE ANDARE", "indirizzo", "address"],
    "civico": ["civico", "CIVICO", "numero_civico", "NUMERO_CIVICO"],
    "tipologia": ["tipologia", "TIPOLOGIA", "immobile", "IMMOBILE", "tipo"],
    "mq": ["mq", "MQ", "m2", "superficie", "SUPERFICIE"],
    "prezzo": ["prezzo", "PREZZO", "prezzo_attuale", "PREZZO_ATTUALE"],
    "prezzo_precedente": ["prezzo_precedente", "PREZZO_PRECEDENTE"],
    "stato": ["stato", "STATO", "lifecycle"],
    "agenzia": ["agenzia", "AGENZIA", "NOME_INSERZIONISTA", "inserzionista"],
    "url": ["url", "URL", "fonte_link", "FONTE_LINK", "link", "LINK"],
    "data_rilevazione": ["data_rilevazione", "DATA_RILEVAZIONE", "prima_rilevazione", "PRIMA_RILEVAZIONE", "data"],
    "note": ["note", "NOTE", "sintesi", "SINTESI", "motivo", "MOTIVO"],
}


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def first(row: dict, names: list[str]) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def raw_url(repo: str, path: str) -> str:
    quoted = "/".join(urllib.parse.quote(p) for p in path.split("/"))
    return f"https://raw.githubusercontent.com/{repo}/main/{quoted}"


def download(repo: str, path: str) -> str | None:
    req = urllib.request.Request(raw_url(repo, path), headers={"User-Agent": "F1-Market-Intelligence/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read(5_000_000).decode("utf-8-sig", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    except Exception:
        return None


def parse_payload(path: str, text: str) -> list[dict]:
    if path.lower().endswith(".json"):
        obj = json.loads(text)
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        if isinstance(obj, dict):
            for key in ("items", "records", "results", "data"):
                if isinstance(obj.get(key), list):
                    return [x for x in obj[key] if isinstance(x, dict)]
            return [obj]
        return []
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t,")
    except Exception:
        dialect = csv.excel
        dialect.delimiter = ";"
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))


def normalize(row: dict, source: dict, source_file: str) -> dict:
    out = {key: first(row, aliases) for key, aliases in ALIASES.items()}
    if out["via"] and out["civico"] and out["civico"] not in out["via"]:
        out["via"] = f"{out['via']} {out['civico']}".strip()
    fingerprint = "|".join([out["comune"], out["via"], out["prezzo"], out["url"], out["tipologia"]])
    out.update({
        "id_external": hashlib.sha256(fingerprint.encode("utf-8", errors="ignore")).hexdigest()[:24],
        "source_name": source.get("name", ""),
        "source_repo": source.get("repo", ""),
        "source_file": source_file,
    })
    return out


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    cfg = load_config()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records: list[dict] = []
    statuses: list[dict] = []

    for source in cfg.get("sources", []):
        mode = source.get("mode", "LINK_ONLY")
        repo = source.get("repo", "")
        if mode == "LINK_ONLY":
            statuses.append({
                "checked_at": now, "name": source.get("name", ""), "repo": repo,
                "mode": mode, "status": "CONNECTED_LINK", "file_found": "",
                "rows_ingested": 0, "url": source.get("url", ""),
                "note": "Collegato al quadro generale; nessun dataset immobiliare importato."
            })
            continue

        found_file = ""
        source_rows: list[dict] = []
        for candidate in source.get("candidate_paths", []):
            text = download(repo, candidate)
            if not text:
                continue
            try:
                parsed = parse_payload(candidate, text)
            except Exception:
                parsed = []
            if parsed:
                found_file = candidate
                source_rows = parsed
                break

        normalized = [normalize(row, source, found_file) for row in source_rows]
        normalized = [r for r in normalized if r["comune"] or r["via"] or r["url"]]
        records.extend(normalized)
        statuses.append({
            "checked_at": now, "name": source.get("name", ""), "repo": repo,
            "mode": mode, "status": "DATA_IMPORTED" if normalized else "NO_DATA",
            "file_found": found_file, "rows_ingested": len(normalized),
            "url": source.get("url", ""),
            "note": "Dataset collegato." if normalized else "Nessun dataset standard disponibile: fonte mantenuta collegata senza inventare dati."
        })

    record_fields = [
        "id_external", "source_name", "source_repo", "source_file", "comune", "via", "civico",
        "tipologia", "mq", "prezzo", "prezzo_precedente", "stato", "agenzia", "url",
        "data_rilevazione", "note"
    ]
    status_fields = ["checked_at", "name", "repo", "mode", "status", "file_found", "rows_ingested", "url", "note"]
    write_csv(OUT_RECORDS, records, record_fields)
    write_csv(OUT_STATUS, statuses, status_fields)
    OUT_SUMMARY.write_text(json.dumps({"checked_at": now, "records": len(records), "sources": statuses}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Cross-repo: {len(records)} record esterni, {len(statuses)} sorgenti controllate")


if __name__ == "__main__":
    main()
