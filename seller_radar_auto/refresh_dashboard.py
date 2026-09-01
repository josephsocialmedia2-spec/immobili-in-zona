#!/usr/bin/env python3
"""Rigenera la dashboard finale distinguendo MASTER e Giro operativo."""
import csv
import html
import json
from datetime import datetime
from pathlib import Path

from f1_remote_bridge import build_import_url

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
QUEUE = DATA / "work_queue.csv"
ROUTE = DATA / "giro_acquisizione.csv"
ROUTE_SUMMARY = DATA / "giro_riepilogo.json"
STATUS = DATA / "source_status.csv"
DASH = ROOT / "dashboard.html"
MUNICIPALITIES = ROOT / "municipalities.csv"
PORTALS = ROOT / "portal_catalog.csv"


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


queue = load_csv(QUEUE)
route = load_csv(ROUTE)
route_summary = load_json(ROUTE_SUMMARY)
status_rows = load_csv(STATUS)
municipalities = [r for r in load_csv(MUNICIPALITIES) if r.get("enabled") == "1"]
portals = [r for r in load_csv(PORTALS) if r.get("enabled") == "1"]
high = sum(1 for r in queue if as_int(r.get("SCORE")) >= 70)
private = sum(1 for r in queue if r.get("INDIZIO_INSERZIONISTA") == "INDIZIO_PRIVATO")
accepted = sum(as_int(r.get("ACCETTATI")) for r in status_rows)
ok = sum(1 for r in status_rows if r.get("STATO") == "OK")

route_by_url = {(r.get("URL") or "").strip(): r for r in route if (r.get("URL") or "").strip()}
state_order = {"FERMATA_PRONTA": 0, "DA_VERIFICARE": 1, "BACKLOG": 2, "STORICO_NON_ATTIVO": 3}
queue_sorted = sorted(
    queue,
    key=lambda r: (
        state_order.get(route_by_url.get((r.get("URL") or "").strip(), {}).get("STATO_GIRO", ""), 9),
        -as_int(r.get("SCORE")),
    ),
)

rows = []
for row in queue_sorted[:1000]:
    score = as_int(row.get("SCORE"))
    score_class = "high" if score >= 70 else "med" if score >= 45 else "low"
    url_key = (row.get("URL") or "").strip()
    route_row = route_by_url.get(url_key, {})
    giro_state = route_row.get("STATO_GIRO") or row.get("STATO_GIRO") or "NON_CLASSIFICATO"
    address = route_row.get("DOVE_ANDRE") or row.get("DOVE_ANDRE") or "DA VERIFICARE"
    remote_url = route_row.get("F1_INDIRIZZO_REMOTO_URL") or build_import_url(row)
    remote_action = (
        f"<a class='remote' href='{esc(remote_url)}' target='_blank' rel='noopener'>APRI IN F1 INDIRIZZO REMOTO</a>"
        if remote_url else "<span class='blocked'>CIVICO DA VERIFICARE</span>"
    )
    source_url = esc(row.get("URL"))
    rows.append(
        f"<tr data-giro='{esc(giro_state)}'><td><span class='score {score_class}'>{score}</span></td>"
        f"<td><span class='giro giro-{esc(giro_state.lower())}'>{esc(giro_state)}</span></td>"
        f"<td>{esc(row.get('PRIORITA'))}</td><td>{esc(row.get('COMUNE'))}</td>"
        f"<td>{esc(row.get('FONTE'))}</td><td>{esc(row.get('INDIZIO_INSERZIONISTA'))}</td>"
        f"<td>{esc(row.get('TITOLO'))}</td><td>{esc(address)}</td>"
        f"<td>{esc(route_row.get('PREZZO') or row.get('PREZZO_OPERATIVO') or row.get('PREZZO') or '—')}</td>"
        f"<td>{esc(row.get('RIBASSI'))}</td><td>{esc(row.get('MOTIVI'))}</td>"
        f"<td><div class='actions'><a href='{source_url}' target='_blank' rel='noopener'>APRI FONTE</a>{remote_action}</div></td></tr>"
    )
if not rows:
    rows = ["<tr><td colspan='12'>Nessuna opportunità rilevata.</td></tr>"]

seller_master = as_int(route_summary.get("seller_master_totali")) or len(queue)
seller_active = as_int(route_summary.get("seller_attivi_master")) or len(queue)
territory = as_int(route_summary.get("nel_territorio_attivo"))
ready = as_int(route_summary.get("fermate_pronte"))
verify = as_int(route_summary.get("indirizzo_da_verificare"))
backlog = as_int(route_summary.get("backlog_fuori_territorio"))
historical = as_int(route_summary.get("storico_non_attivo"))
assigned = as_int(route_summary.get("fermate_assegnate_team"))

DASH.write_text(f"""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>F1 Seller Radar · Giro Acquisizione</title><style>
body{{font-family:Segoe UI,Arial;background:#0c0f0d;color:#eee;padding:22px;margin:0}}h1{{margin-bottom:4px}}.subtitle{{color:#b8c0ba}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin:20px 0}}.card{{background:#151a17;border:1px solid #2c3630;padding:13px;border-radius:12px}}.card b{{display:block;font-size:26px;margin-top:4px}}.primary{{border-color:#4a8f5c}}.warning{{border-color:#9a7a2f}}.muted{{opacity:.82}}.legend{{background:#121613;border:1px solid #2c3630;border-radius:10px;padding:12px;margin:14px 0;line-height:1.5}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;background:#141815;min-width:1200px}}th,td{{padding:8px;border-bottom:1px solid #2c332f;text-align:left;font-size:13px;vertical-align:top}}a{{color:#78e08f}}.actions{{display:grid;gap:8px;min-width:190px}}.remote{{display:block;background:#174f2a;color:white;padding:8px;border-radius:7px;text-decoration:none;font-weight:800}}.blocked{{color:#d7b95b;font-size:11px}}.score,.giro{{padding:4px 6px;border-radius:7px;white-space:nowrap}}.high{{background:#5f2020}}.med{{background:#5d4b17}}.low{{background:#25442f}}.giro-fermata_pronta{{background:#174f2a}}.giro-da_verificare{{background:#5d4b17}}.giro-backlog{{background:#27303a}}.giro-storico_non_attivo{{background:#3c3c3c;color:#bbb}}@media(max-width:700px){{body{{padding:12px}}.card b{{font-size:22px}}}}
</style></head><body><h1>F1 SELLER RADAR · GIRO ACQUISIZIONE</h1><div class='subtitle'>MASTER completo + filtro operativo Susa 20 km · Aggiornato {datetime.now().strftime('%d/%m/%Y %H:%M')}</div>
<div class='cards'>
<div class='card'>SELLER MASTER TOTALI<b>{seller_master}</b></div>
<div class='card'>SELLER ATTIVI MASTER<b>{seller_active}</b></div>
<div class='card primary'>NEL TERRITORIO ATTIVO<b>{territory}</b></div>
<div class='card primary'>FERMATE PRONTE<b>{ready}</b></div>
<div class='card warning'>INDIRIZZO DA VERIFICARE<b>{verify}</b></div>
<div class='card'>BACKLOG FUORI TERRITORIO<b>{backlog}</b></div>
<div class='card'>ASSEGNATE AL TEAM<b>{assigned}</b></div>
<div class='card muted'>STORICO NON ATTIVO<b>{historical}</b></div>
<div class='card muted'>PRIORITÀ ALTA<b>{high}</b></div>
<div class='card muted'>INDIZI PRIVATO<b>{private}</b></div>
<div class='card muted'>QUERY OK<b>{ok}/{len(status_rows)}</b></div>
<div class='card muted'>TERRITORI OPERATIVI<b>{len(municipalities)}</b></div>
<div class='card muted'>PORTALI<b>{len(portals)}</b></div>
</div>
<div class='legend'><b>Come leggere i numeri:</b> il MASTER non viene tagliato dal raggio operativo. Susa +20 km decide soltanto cosa entra nel Giro di oggi. “FERMATA_PRONTA” significa indirizzo utilizzabile; “DA_VERIFICARE” resta nel territorio ma richiede controllo; “BACKLOG” è valido ma fuori dal giro corrente.</div>
<div class='table-wrap'><table><thead><tr><th>Score</th><th>Stato Giro</th><th>Priorità</th><th>Comune</th><th>Fonte</th><th>Inserzionista</th><th>Immobile</th><th>Indirizzo</th><th>Prezzo</th><th>Ribassi</th><th>Motivi</th><th>Azioni</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
</body></html>""", encoding="utf-8")
print(
    f"DASHBOARD FINALE: master={seller_master}, attivi={seller_active}, territorio={territory}, "
    f"fermate={ready}, verifica={verify}, backlog={backlog}, assegnate={assigned}."
)
