#!/usr/bin/env python3
"""Unisce discovery per Comune nello state persistente e traccia il ciclo di vita.

Una mancata rilevazione NON viene trattata come vendita. Dopo 3 cicli sani senza
ritrovare il risultato diventa POSSIBILE_USCITA; dopo 7 diventa USCITO_MERCATO.
Se ricompare viene marcato RELISTED e il contatore assenze viene azzerato.
"""
import csv, hashlib, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"; DATA.mkdir(parents=True, exist_ok=True)
INPUT = ROOT / "discovery_results"; STATE = DATA / "state.json"; STATUS = DATA / "ddg_source_status.csv"
OUT_STATES = {"POSSIBILE_USCITA", "USCITO_MERCATO", "REMOVED", "EXPIRED", "OUT"}
TRACKED_ENGINES = {"DDG_MATRIX_V1", "PUBLIC_DORK_MATRIX_V3", "PUBLIC_DORK_MATRIX_V4"}


def now(): return datetime.now(timezone.utc).isoformat()
def key(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()[:20]
def set_lifecycle(x, value):
    if x.get("lifecycle") != value:
        x["lifecycle"] = value
        x["last_status_change_at"] = now()

def merge_signal(old, new):
    vals = []
    for src in (old, new):
        for v in str(src or "").split(","):
            v = v.strip()
            if v and v not in vals:
                vals.append(v)
    return ",".join(vals)

try:
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"items": {}}
except Exception:
    state = {"items": {}}
items = state.setdefault("items", {})
for item_id, x in list(items.items()):
    if x.get("discovery_engine") in {"DUCKDUCKGO_HTML", "DUCKDUCKGO_HTML_V2", "DUCKDUCKGO_AGGREGATED_V3"}:
        del items[item_id]

statuses = []; current = []
for path in sorted(INPUT.rglob("*.json")) if INPUT.exists() else []:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"SKIP {path}: {e}"); continue
    statuses.extend(doc.get("status") or [])
    current.extend(doc.get("results") or [])

ok_counts = Counter()
for s in statuses:
    if str(s.get("STATO", "")).upper() == "OK" and s.get("COMUNE"):
        ok_counts[s["COMUNE"]] += 1
healthy = {c for c, n in ok_counts.items() if n >= 3}
seen_urls = set(); seen_ids = set()

for r in current:
    url = (r.get("url") or "").strip()
    if not url or url in seen_urls:
        continue
    seen_urls.add(url)
    i = key(url); seen_ids.add(i)
    p = r.get("price")
    engine = r.get("discovery_engine") or "PUBLIC_DORK_MATRIX_V4"
    common = {
        "opportunity_type": r.get("opportunity_type", "RESIDENZIALE"),
        "lead_target": r.get("lead_target", "IMMOBILE"),
        "project_stage": r.get("project_stage", ""),
        "commercial_goal": r.get("commercial_goal", "ACQUISIZIONE IMMOBILE"),
    }
    if i not in items:
        items[i] = {
            "id": i, "comune": r.get("comune", ""), "fonte": r.get("fonte", ""),
            "url": url, "title": r.get("title", "")[:220], "snippet": r.get("snippet", "")[:700],
            "price_history": [], "seller_hint": r.get("seller_hint", "NON_DETERMINATO"),
            "private_intent": bool(r.get("private_intent")),
            "market_signal": r.get("market_signal", "VENDITA"), "query_label": r.get("query_label", ""),
            "first_seen": now(), "last_seen": now(), "checks": 1, "lifecycle": "NEW", "missed_checks": 0,
            "domain_rule": r.get("domain_rule", ""), "path_rule": r.get("path_rule", ""),
            "discovery_engine": engine, **common,
        }
    else:
        x = items[i]; previous = x.get("lifecycle", "")
        x["last_seen"] = now(); x["checks"] = int(x.get("checks", 0)) + 1; x["missed_checks"] = 0
        x["title"] = r.get("title", "")[:220] or x.get("title", "")
        x["snippet"] = r.get("snippet", "")[:700] or x.get("snippet", "")
        x["fonte"] = r.get("fonte", "") or x.get("fonte", "")
        x["private_intent"] = bool(x.get("private_intent")) or bool(r.get("private_intent"))
        x["discovery_engine"] = engine
        x["market_signal"] = merge_signal(x.get("market_signal"), r.get("market_signal"))
        x["query_label"] = r.get("query_label", "") or x.get("query_label", "")
        for k, v in common.items():
            if v:
                x[k] = v
        if r.get("seller_hint") and r.get("seller_hint") != "NON_DETERMINATO":
            x["seller_hint"] = r["seller_hint"]
        if previous in OUT_STATES:
            x["reentries"] = int(x.get("reentries", 0)) + 1
            x["last_reentry_at"] = now(); set_lifecycle(x, "RELISTED")
        elif previous == "RELISTED":
            set_lifecycle(x, "TRACKED")
        elif previous == "NEW" and x["checks"] > 1:
            set_lifecycle(x, "TRACKED")
    if p:
        hist = items[i].setdefault("price_history", [])
        if not hist or hist[-1].get("price") != p:
            hist.append({"at": now(), "price": p})
            items[i]["price_history"] = hist[-20:]

for i, x in items.items():
    if i in seen_ids or x.get("discovery_engine") not in TRACKED_ENGINES:
        continue
    comune = x.get("comune", "")
    if comune not in healthy:
        continue
    missed = int(x.get("missed_checks", 0)) + 1
    x["missed_checks"] = missed; x["last_missing_at"] = now()
    if missed >= 7:
        set_lifecycle(x, "USCITO_MERCATO")
    elif missed >= 3:
        set_lifecycle(x, "POSSIBILE_USCITA")

state["items"] = items
state["matrix_discovery_updated_at"] = now()
state["healthy_municipalities_last_cycle"] = sorted(healthy)
STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
fields = ["FONTE", "COMUNE", "STATO", "ULTIMO_CONTROLLO", "RISULTATI_GREZZI", "ACCETTATI", "MESSAGGIO", "QUERY"]
with STATUS.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(statuses)
print(f"MERGE DISCOVERY: {len(seen_urls)} URL unici, {len(items)} storico, {len(healthy)} comuni con ciclo sano, {sum(1 for s in statuses if s.get('STATO')=='OK')}/{len(statuses)} query OK.")
