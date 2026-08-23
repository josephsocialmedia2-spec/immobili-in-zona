#!/usr/bin/env python3
"""Rigenera il dashboard finale, includendo il passaggio al modulo locale."""
import csv
import html
from datetime import datetime
from pathlib import Path

from f1_remote_bridge import build_import_url


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
QUEUE = DATA / "work_queue.csv"
STATUS = DATA / "source_status.csv"
DASH = ROOT / "dashboard.html"
MUNICIPALITIES = ROOT / "municipalities.csv"
PORTALS = ROOT / "portal_catalog.csv"


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


queue = load_csv(QUEUE)
status_rows = load_csv(STATUS)
municipalities = [r for r in load_csv(MUNICIPALITIES) if r.get("enabled") == "1"]
portals = [r for r in load_csv(PORTALS) if r.get("enabled") == "1"]
high = sum(1 for r in queue if int(r.get("SCORE") or 0) >= 70)
private = sum(1 for r in queue if r.get("INDIZIO_INSERZIONISTA") == "INDIZIO_PRIVATO")
accepted = sum(int(r.get("ACCETTATI") or 0) for r in status_rows)
ok = sum(1 for r in status_rows if r.get("STATO") == "OK")

rows = []
for row in queue[:1000]:
    score = int(row.get("SCORE") or 0)
    score_class = "high" if score >= 70 else "med" if score >= 45 else "low"
    remote_url = build_import_url(row)
    remote_action = (
        f"<a class='remote' href='{esc(remote_url)}' target='_blank' rel='noopener'>APRI IN F1 INDIRIZZO REMOTO</a>"
        if remote_url else "<span class='blocked'>CIVICO DA VERIFICARE</span>"
    )
    source_url = esc(row.get("URL"))
    rows.append(
        f"<tr><td><span class='score {score_class}'>{score}</span></td>"
        f"<td>{esc(row.get('PRIORITA'))}</td><td>{esc(row.get('COMUNE'))}</td>"
        f"<td>{esc(row.get('FONTE'))}</td><td>{esc(row.get('INDIZIO_INSERZIONISTA'))}</td>"
        f"<td>{esc(row.get('TITOLO'))}</td><td>{esc(row.get('DOVE_ANDRE') or 'DA VERIFICARE')}</td>"
        f"<td>{esc(row.get('PREZZO_OPERATIVO') or row.get('PREZZO') or '—')}</td>"
        f"<td>{esc(row.get('RIBASSI'))}</td><td>{esc(row.get('MOTIVI'))}</td>"
        f"<td><div class='actions'><a href='{source_url}' target='_blank' rel='noopener'>APRI FONTE</a>{remote_action}</div></td></tr>"
    )
if not rows:
    rows = ["<tr><td colspan='11'>Nessuna opportunità rilevata.</td></tr>"]

DASH.write_text(f"""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>F1 Seller Radar</title><style>
body{{font-family:Segoe UI,Arial;background:#0c0f0d;color:#eee;padding:22px}}.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}}.card{{background:#151a17;border:1px solid #2c3630;padding:14px;border-radius:12px}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;background:#141815}}th,td{{padding:8px;border-bottom:1px solid #2c332f;text-align:left;font-size:13px;vertical-align:top}}a{{color:#78e08f}}.actions{{display:grid;gap:8px;min-width:190px}}.remote{{display:block;background:#174f2a;color:white;padding:8px;border-radius:7px;text-decoration:none;font-weight:800}}.blocked{{color:#d7b95b;font-size:11px}}.score{{padding:4px 6px;border-radius:7px}}.high{{background:#5f2020}}.med{{background:#5d4b17}}.low{{background:#25442f}}
</style></head><body><h1>F1 SELLER RADAR</h1><div>Discovery e approfondimento locale · Aggiornato {datetime.now().strftime('%d/%m/%Y %H:%M')}</div><div class='cards'><div class='card'>Opportunità <b>{len(queue)}</b></div><div class='card'>Priorità alta <b>{high}</b></div><div class='card'>Indizi privato <b>{private}</b></div><div class='card'>Accettati ciclo <b>{accepted}</b></div><div class='card'>Query OK <b>{ok}/{len(status_rows)}</b></div><div class='card'>Territori <b>{len(municipalities)}</b></div><div class='card'>Portali <b>{len(portals)}</b></div></div><div class='table-wrap'><table><thead><tr><th>Score</th><th>Priorità</th><th>Comune</th><th>Fonte</th><th>Inserzionista</th><th>Immobile</th><th>Indirizzo</th><th>Prezzo</th><th>Ribassi</th><th>Motivi</th><th>Azioni</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></body></html>""", encoding="utf-8")
print(f"DASHBOARD FINALE: {len(queue)} opportunità, collegamento locale F1 attivo sugli indirizzi con civico.")
