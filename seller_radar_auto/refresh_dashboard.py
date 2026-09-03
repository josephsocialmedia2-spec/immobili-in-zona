#!/usr/bin/env python3
"""Rigenera la dashboard finale usando esattamente il MASTER preservato da 660 seller."""
import csv
import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from f1_remote_bridge import build_import_url

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MASTER = DATA / "seller_master_660_classificato.csv"
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


def row_url(row: dict) -> str:
    return (row.get("URL") or "").strip()


def comune_key(row: dict) -> str:
    # Ordinamento principale richiesto dall'utente: tutti i seller raggruppati per paese/comune.
    return (row.get("COMUNE") or "ZZZ_SENZA_COMUNE").strip().casefold()


master_rows = load_csv(MASTER)
route = load_csv(ROUTE)
route_summary = load_json(ROUTE_SUMMARY)
status_rows = load_csv(STATUS)
municipalities = [r for r in load_csv(MUNICIPALITIES) if r.get("enabled") == "1"]
portals = [r for r in load_csv(PORTALS) if r.get("enabled") == "1"]

# Vincolo richiesto: questa vista rappresenta ESATTAMENTE i 660 seller del master.
# Giro, territorio, qualità e stato possono classificare le righe ma non aggiungerle o eliminarle.
if len(master_rows) != 660:
    raise SystemExit(f"FAIL MASTER: attesi esattamente 660 seller, trovati {len(master_rows)}")
if any((r.get("MASTER_PRESERVATO") or "").strip().upper() != "SI" for r in master_rows):
    raise SystemExit("FAIL MASTER: almeno una delle 660 righe non risulta preservata")

master_ids = [(r.get("MASTER_660_ID") or "").strip() for r in master_rows]
if len(set(master_ids)) != 660 or any(not value for value in master_ids):
    raise SystemExit("FAIL MASTER: gli ID MASTER_660_ID non sono 660 univoci e valorizzati")

high = sum(1 for r in master_rows if as_int(r.get("SCORE")) >= 70)
private = sum(1 for r in master_rows if r.get("INDIZIO_INSERZIONISTA") == "INDIZIO_PRIVATO")
ok = sum(1 for r in status_rows if r.get("STATO") == "OK")

route_by_url = {row_url(r): r for r in route if row_url(r)}
state_order = {"FERMATA_PRONTA": 0, "DA_VERIFICARE": 1, "BACKLOG": 2, "STORICO_NON_ATTIVO": 3, "MASTER": 4}

# IMPORTANTE: il COMUNE è la prima chiave. Solo dentro lo stesso comune si ordina per stato e score.
master_sorted = sorted(
    master_rows,
    key=lambda r: (
        comune_key(r),
        state_order.get(route_by_url.get(row_url(r), {}).get("STATO_GIRO", "MASTER"), 9),
        -as_int(r.get("SCORE")),
        as_int(r.get("MASTER_660_ID")),
    ),
)

tipologia_counts = Counter((r.get("TIPOLOGIA_REALE_INFERITA") or "NON_CLASSIFICATO").strip() for r in master_rows)
asta_count = sum(1 for r in master_rows if (r.get("ASTA_RILEVATA") or "").strip().upper() == "SI")

rows = []
for row in master_sorted:
    score = as_int(row.get("SCORE"))
    score_class = "high" if score >= 70 else "med" if score >= 45 else "low"
    url_key = row_url(row)
    route_row = route_by_url.get(url_key, {})
    giro_state = route_row.get("STATO_GIRO") or "MASTER"
    address = route_row.get("DOVE_ANDRE") or row.get("DOVE_ANDRE") or "DA VERIFICARE"
    remote_url = route_row.get("F1_INDIRIZZO_REMOTO_URL") or build_import_url(row)
    remote_action = (
        f"<a class='remote' href='{esc(remote_url)}' target='_blank' rel='noopener'>APRI IN F1 INDIRIZZO REMOTO</a>"
        if remote_url else "<span class='blocked'>CIVICO DA VERIFICARE</span>"
    )
    source_url = esc(row.get("URL"))
    source_action = (
        f"<a href='{source_url}' target='_blank' rel='noopener'>APRI FONTE</a>"
        if source_url else "<span class='blocked'>FONTE NON DISPONIBILE</span>"
    )
    tipologia = (row.get("TIPOLOGIA_REALE_INFERITA") or "NON_CLASSIFICATO").strip()
    asta = (row.get("ASTA_RILEVATA") or "NO").strip().upper()
    master_id = row.get("MASTER_660_ID")
    rows.append(
        f"<tr class='seller-row' data-giro='{esc(giro_state)}' data-tipologia='{esc(tipologia)}' data-asta='{esc(asta)}' data-master-id='{esc(master_id)}' data-comune='{esc(row.get('COMUNE'))}'>"
        f"<td>{esc(master_id)}</td><td><span class='score {score_class}'>{score}</span></td>"
        f"<td><span class='giro giro-{esc(giro_state.lower())}'>{esc(giro_state)}</span></td>"
        f"<td>{esc(tipologia)}</td><td>{'SI' if asta == 'SI' else '—'}</td>"
        f"<td>{esc(row.get('PRIORITA'))}</td><td><b>{esc(row.get('COMUNE'))}</b></td>"
        f"<td>{esc(row.get('FONTE'))}</td><td>{esc(row.get('INDIZIO_INSERZIONISTA'))}</td>"
        f"<td>{esc(row.get('TITOLO'))}</td><td>{esc(address)}</td>"
        f"<td>{esc(route_row.get('PREZZO') or row.get('PREZZO_OPERATIVO') or row.get('PREZZO') or '—')}</td>"
        f"<td>{esc(row.get('RIBASSI'))}</td><td>{esc(row.get('MOTIVI'))}</td>"
        f"<td><div class='actions'>{source_action}{remote_action}</div></td></tr>"
    )

seller_master = len(master_rows)
territory = as_int(route_summary.get("nel_territorio_attivo"))
ready = as_int(route_summary.get("fermate_pronte"))
verify = as_int(route_summary.get("indirizzo_da_verificare"))
backlog = as_int(route_summary.get("backlog_fuori_territorio"))
historical = as_int(route_summary.get("storico_non_attivo"))
assigned = as_int(route_summary.get("fermate_assegnate_team"))

filter_buttons = [f"<button class='filter active' data-filter='ALL'>TUTTI <b>{seller_master}</b></button>"]
for tipologia, count in sorted(tipologia_counts.items(), key=lambda x: (-x[1], x[0])):
    filter_buttons.append(
        f"<button class='filter' data-filter='{esc(tipologia)}'>{esc(tipologia.replace('_', ' '))} <b>{count}</b></button>"
    )
filter_buttons.append(f"<button class='filter' data-filter='ASTE'>ASTE <b>{asta_count}</b></button>")

DASH.write_text(f"""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>F1 Seller Radar · Master 660</title><style>
body{{font-family:Segoe UI,Arial;background:#0c0f0d;color:#eee;padding:22px;margin:0}}h1{{margin-bottom:4px}}.subtitle{{color:#b8c0ba}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin:20px 0}}.card{{background:#151a17;border:1px solid #2c3630;padding:13px;border-radius:12px}}.card b{{display:block;font-size:26px;margin-top:4px}}.master-card{{border:2px solid #78e08f;background:#102218}}.primary{{border-color:#4a8f5c}}.warning{{border-color:#9a7a2f}}.muted{{opacity:.82}}.legend{{background:#121613;border:1px solid #2c3630;border-radius:10px;padding:12px;margin:14px 0;line-height:1.5}}.filters{{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}}.filter{{background:#171d19;color:#eee;border:1px solid #354139;border-radius:9px;padding:8px 10px;cursor:pointer}}.filter.active{{border-color:#78e08f;background:#173922}}.filter b{{margin-left:5px}}.visible-count{{font-weight:800;margin:12px 0;color:#9ce8ad}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;background:#141815;min-width:1500px}}th,td{{padding:8px;border-bottom:1px solid #2c332f;text-align:left;font-size:13px;vertical-align:top}}a{{color:#78e08f}}.actions{{display:grid;gap:8px;min-width:190px}}.remote{{display:block;background:#174f2a;color:white;padding:8px;border-radius:7px;text-decoration:none;font-weight:800}}.blocked{{color:#d7b95b;font-size:11px}}.score,.giro{{padding:4px 6px;border-radius:7px;white-space:nowrap}}.high{{background:#5f2020}}.med{{background:#5d4b17}}.low{{background:#25442f}}.giro-fermata_pronta{{background:#174f2a}}.giro-da_verificare{{background:#5d4b17}}.giro-backlog{{background:#27303a}}.giro-storico_non_attivo{{background:#3c3c3c;color:#bbb}}.giro-master{{background:#26372b}}@media(max-width:700px){{body{{padding:12px}}.card b{{font-size:22px}}}}
</style></head><body><h1>F1 SELLER RADAR · MASTER COMPLETO</h1><div class='subtitle'>Vista completa dei 660 seller preservati, ordinati per paese/comune. I filtri cambiano solo la vista · Aggiornato {datetime.now().strftime('%d/%m/%Y %H:%M')}</div>
<div class='cards'>
<div class='card master-card'>SELLER TOTALI<b>{seller_master}</b></div>
<div class='card primary'>NEL TERRITORIO ATTIVO<b>{territory}</b></div>
<div class='card primary'>FERMATE PRONTE<b>{ready}</b></div>
<div class='card warning'>INDIRIZZO DA VERIFICARE<b>{verify}</b></div>
<div class='card'>BACKLOG FUORI TERRITORIO<b>{backlog}</b></div>
<div class='card'>ASSEGNATE AL TEAM<b>{assigned}</b></div>
<div class='card muted'>STORICO NON ATTIVO<b>{historical}</b></div>
<div class='card muted'>PRIORITÀ ALTA<b>{high}</b></div>
<div class='card muted'>INDIZI PRIVATO<b>{private}</b></div>
<div class='card muted'>ASTE RILEVATE<b>{asta_count}</b></div>
<div class='card muted'>QUERY OK<b>{ok}/{len(status_rows)}</b></div>
<div class='card muted'>TERRITORI OPERATIVI<b>{len(municipalities)}</b></div>
<div class='card muted'>PORTALI<b>{len(portals)}</b></div>
</div>
<div class='legend'><b>Ordine della lista:</b> PAese/Comune → Stato Giro → Score. Tutti i seller dello stesso paese sono quindi consecutivi. Questa vista contiene esattamente i 660 seller del MASTER: i filtri non cancellano righe.</div>
<div class='filters'>{''.join(filter_buttons)}</div>
<div class='visible-count'>VISIBILI: <span id='visibleCount'>{seller_master}</span> / {seller_master}</div>
<div class='table-wrap'><table><thead><tr><th>ID Master</th><th>Score</th><th>Stato Giro</th><th>Tipologia</th><th>Asta</th><th>Priorità</th><th>Comune</th><th>Fonte</th><th>Inserzionista</th><th>Immobile</th><th>Indirizzo</th><th>Prezzo</th><th>Ribassi</th><th>Motivi</th><th>Azioni</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<script>
const buttons=[...document.querySelectorAll('.filter')];
const sellerRows=[...document.querySelectorAll('.seller-row')];
const visibleCount=document.getElementById('visibleCount');
function applyFilter(value){{
  let shown=0;
  sellerRows.forEach(row=>{{
    const match=value==='ALL' || (value==='ASTE' ? row.dataset.asta==='SI' : row.dataset.tipologia===value);
    row.style.display=match?'':'none';
    if(match) shown++;
  }});
  visibleCount.textContent=shown;
  buttons.forEach(b=>b.classList.toggle('active',b.dataset.filter===value));
}}
buttons.forEach(button=>button.addEventListener('click',()=>applyFilter(button.dataset.filter)));
</script>
</body></html>""", encoding="utf-8")

rendered = DASH.read_text(encoding="utf-8")
rendered_rows = rendered.count("class='seller-row'")
if rendered_rows != 660:
    raise SystemExit(f"FAIL DASHBOARD: righe renderizzate={rendered_rows}, attese=660")
if "SELLER TOTALI<b>660</b>" not in rendered or "VISIBILI: <span id='visibleCount'>660</span> / 660" not in rendered:
    raise SystemExit("FAIL DASHBOARD: contatori 660 non presenti correttamente")

# QA dell'ordinamento per comune: la sequenza deve essere monotona alfabeticamente.
comuni_sorted = [comune_key(r) for r in master_sorted]
if comuni_sorted != sorted(comuni_sorted):
    raise SystemExit("FAIL DASHBOARD: seller non ordinati per comune")

print(
    f"DASHBOARD MASTER 660: seller_totali=660, territorio={territory}, fermate={ready}, "
    f"verifica={verify}, backlog={backlog}, assegnate={assigned}, aste={asta_count}."
)
print("PASS DASHBOARD MASTER 660 | 660 righe renderizzate e ordinate per comune; nessuna aggiunta, nessuna eliminazione")
