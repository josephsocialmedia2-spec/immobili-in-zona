#!/usr/bin/env python3
"""QA deterministico del Giro Acquisizione.

Fallisce se il master viene tagliato dal filtro Susa 20 km, se una fermata/team
finisce fuori territorio, o se i contatori non corrispondono ai CSV generati.
"""
import csv
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
QUEUE = DATA / "work_queue.csv"
MASTER = DATA / "giro_acquisizione.csv"
TODAY = DATA / "giro_acquisizione_oggi.csv"
VERIFY = DATA / "giro_da_verificare.csv"
BACKLOG = DATA / "giro_backlog.csv"
TEAM = DATA / "giro_funzionari.csv"
SUMMARY = DATA / "giro_riepilogo.json"
MUNICIPALITIES = ROOT / "municipalities.csv"


def read_csv(path):
    if not path.exists():
        raise AssertionError(f"File obbligatorio assente: {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm(value):
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def as_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


queue = read_csv(QUEUE)
master = read_csv(MASTER)
today = read_csv(TODAY)
verify = read_csv(VERIFY)
backlog = read_csv(BACKLOG)
team = read_csv(TEAM)
municipalities = read_csv(MUNICIPALITIES)
assert SUMMARY.exists(), "File obbligatorio assente: giro_riepilogo.json"
summary = json.loads(SUMMARY.read_text(encoding="utf-8"))

active_towns = {norm(r.get("comune")) for r in municipalities if r.get("enabled") == "1" and norm(r.get("comune"))}
assert "susa" in active_towns, "Susa non è nel territorio operativo"

# 1. Il Giro master deve essere una classificazione della coda completa, non un sottoinsieme.
assert len(master) == len(queue), f"Master tagliato: queue={len(queue)} giro_master={len(master)}"
queue_urls = [(r.get("URL") or "").strip() for r in queue]
master_urls = [(r.get("URL") or "").strip() for r in master]
assert sorted(queue_urls) == sorted(master_urls), "Gli URL del Giro master non coincidono con work_queue.csv"

# 2. Il filtro operativo deve agire soltanto sul Giro di oggi.
for r in today:
    assert r.get("TERRITORIO_OPERATIVO") == "SI", f"Record TODAY fuori territorio: {r.get('COMUNE')}"
    assert norm(r.get("COMUNE")) in active_towns, f"Comune TODAY non enabled: {r.get('COMUNE')}"
    assert r.get("STATO_GIRO") in {"FERMATA_PRONTA", "DA_VERIFICARE"}, f"Stato TODAY inatteso: {r.get('STATO_GIRO')}"

for r in verify:
    assert r.get("STATO_GIRO") == "DA_VERIFICARE", "File verifica contiene record non DA_VERIFICARE"
    assert norm(r.get("COMUNE")) in active_towns, "Record da verificare fuori territorio"

for r in backlog:
    assert r.get("STATO_GIRO") == "BACKLOG", "File backlog contiene record con stato diverso da BACKLOG"
    assert norm(r.get("COMUNE")) not in active_towns, f"BACKLOG dentro territorio operativo: {r.get('COMUNE')}"

# 3. Nessun funzionario deve ricevere record fuori territorio o non pronto.
for r in team:
    assert r.get("STATO_ASSEGNAZIONE") == "ASSEGNATO", "Team contiene riga non assegnata"
    assert r.get("STATO_GIRO") == "FERMATA_PRONTA", "Team contiene riga non pronta"
    assert r.get("TERRITORIO_OPERATIVO") == "SI", "Team contiene riga fuori territorio"
    assert norm(r.get("COMUNE")) in active_towns, f"Team fuori Susa+20: {r.get('COMUNE')}"

# 4. I contatori pubblicati devono essere derivati dai dati, non hard-coded.
expected = {
    "seller_master_totali": len(master),
    "seller_attivi_master": sum(1 for r in master if r.get("STATO_GIRO") != "STORICO_NON_ATTIVO"),
    "storico_non_attivo": sum(1 for r in master if r.get("STATO_GIRO") == "STORICO_NON_ATTIVO"),
    "nel_territorio_attivo": len(today),
    "fermate_pronte": sum(1 for r in master if r.get("STATO_GIRO") == "FERMATA_PRONTA"),
    "indirizzo_da_verificare": len(verify),
    "backlog_fuori_territorio": len(backlog),
    "fermate_assegnate_team": len(team),
    "territori_operativi_configurati": len(active_towns),
}
for key, value in expected.items():
    assert as_int(summary.get(key)) == value, f"Contatore {key} errato: json={summary.get(key)} atteso={value}"

# 5. Partizione dei seller attivi: territorio + backlog = attivi master.
assert len(today) + len(backlog) == expected["seller_attivi_master"], (
    "Partizione seller attivi incoerente: territorio + backlog != seller_attivi_master"
)

print(
    "PASS GIRO QA | "
    f"master={len(master)} attivi={expected['seller_attivi_master']} territorio={len(today)} "
    f"fermate={expected['fermate_pronte']} verifica={len(verify)} backlog={len(backlog)} team={len(team)}"
)
