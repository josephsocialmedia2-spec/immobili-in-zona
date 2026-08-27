#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INTEL = ROOT / "data" / "intelligence"
OUT = ROOT / "appointment_brief.html"


def load_csv(name: str) -> list[dict]:
    path = INTEL / name
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t,")
        return list(csv.DictReader(text.splitlines(), dialect=dialect))
    except Exception:
        delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
        return list(csv.DictReader(text.splitlines(), delimiter=delimiter))


def num(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("€", "").replace("EUR", "").replace(" ", "")
    if not s:
        return None
    try:
        if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
            return float(s)
        if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
            return float(s.replace(".", "").replace(",", "."))
        if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?", s):
            return float(s.replace(",", ""))
        return float(s.replace(",", "."))
    except Exception:
        return None


def truth(v) -> bool:
    return str(v or "").strip().lower() in {"true", "1", "si", "sì", "yes"}


def primary_items() -> list[dict]:
    out = []
    for r in load_csv("immobili_snapshot.csv"):
        out.append({
            "id": r.get("id", ""), "comune": r.get("comune", ""), "via": r.get("via", ""),
            "strada": r.get("strada", ""), "tipologia": r.get("tipologia", ""), "titolo": r.get("titolo", ""),
            "fonte": r.get("fonte", ""), "agenzia": r.get("agenzia", ""), "url": r.get("url", ""),
            "stato": r.get("stato", ""), "attivo": truth(r.get("attivo")),
            "venduto_confermato": truth(r.get("venduto_confermato")),
            "giorni_mercato": num(r.get("giorni_mercato")), "prezzo": num(r.get("prezzo")),
            "prezzo_mq": num(r.get("prezzo_mq")), "numero_ribassi": num(r.get("numero_ribassi")) or 0,
            "giorni_al_primo_ribasso": num(r.get("giorni_al_primo_ribasso")),
            "ribasso_totale_pct": num(r.get("ribasso_totale_pct")), "origine": "RADAR CENTRALE"
        })
    return out


def external_items() -> list[dict]:
    out = []
    for r in load_csv("external_records.csv"):
        state = r.get("stato", "ESTERNO")
        via = r.get("via", "")
        out.append({
            "id": r.get("id_external", ""), "comune": r.get("comune", ""), "via": via, "strada": via,
            "tipologia": r.get("tipologia", ""), "titolo": r.get("note", ""), "fonte": r.get("source_name", ""),
            "agenzia": r.get("agenzia", ""), "url": r.get("url", ""), "stato": state,
            "attivo": not any(k in state.lower() for k in ("uscit", "scadut", "rimos", "vendut")),
            "venduto_confermato": "venduto" in state.lower(), "giorni_mercato": None,
            "prezzo": num(r.get("prezzo")), "prezzo_mq": None, "numero_ribassi": 0,
            "giorni_al_primo_ribasso": None, "ribasso_totale_pct": None, "origine": r.get("source_repo", "")
        })
    return out


def dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in items:
        key = (r.get("url") or "").strip().lower()
        if not key:
            key = "|".join([str(r.get("comune", "")).lower(), str(r.get("via", "")).lower(), str(r.get("prezzo", "")), str(r.get("tipologia", "")).lower()])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main() -> None:
    items = dedupe(primary_items() + external_items())
    data = {
        "items": items,
        "comuni": load_csv("kpi_comuni.csv"),
        "vie": load_csv("kpi_vie.csv"),
        "tipi": load_csv("kpi_tipologie.csv"),
        "agenzie": load_csv("kpi_agenzie.csv"),
        "eventi": load_csv("eventi_mercato.csv")[-800:],
        "repos": load_csv("repo_status.csv"),
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>F1 Brief Appuntamento</title><style>
:root{{--g:#39F28A;--bg:#070907;--p:#101510;--line:#2b372e;--mut:#aeb7b0;--warn:#ffd166}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:#fff;font-family:Arial,sans-serif}}header{{padding:18px;border-bottom:1px solid var(--line);position:sticky;top:0;background:#070907f2;z-index:5}}h1{{margin:0;font-size:22px}}header p{{margin:4px 0;color:var(--mut)}}main{{max-width:1450px;margin:auto;padding:16px}}.filters{{display:grid;grid-template-columns:1fr 1fr auto auto;gap:9px}}select,input,button{{padding:12px;border-radius:10px;border:1px solid var(--line);background:#111713;color:#fff}}button{{background:var(--g);color:#07100a;font-weight:900}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:9px;margin:14px 0}}.card,.panel{{background:var(--p);border:1px solid var(--line);border-radius:12px;padding:12px}}.card small{{display:block;color:var(--mut);font-size:9px;text-transform:uppercase}}.card b{{font-size:21px}}h2{{font-size:15px;color:var(--g);margin:22px 0 8px}}.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}.panel{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:700px}}th,td{{padding:8px;border-bottom:1px solid var(--line);font-size:11px;text-align:left}}th{{color:var(--mut)}}a{{color:var(--g)}}.note{{font-size:11px;color:var(--warn);margin:10px 0}}.ok{{color:var(--g)}}.no{{color:var(--warn)}}@media(max-width:800px){{.filters,.grid2{{grid-template-columns:1fr}}}}@media print{{header{{position:static}}button{{display:none}}body{{background:#fff;color:#111}}.panel,.card{{background:#fff;border-color:#ccc}}}}
</style></head><body><header><h1>F1 IMMOBILIARE — BRIEF APPUNTAMENTO</h1><p>Comune → via → prezzi → tempi → ribassi → tipologie → agenzie → movimenti</p></header><main><div class="filters"><select id="comune"><option value="">Seleziona Comune</option></select><input id="via" placeholder="Via / borgata / località"><button onclick="render()">ANALIZZA</button><button onclick="window.print()">STAMPA</button></div><div id="title"></div><div class="cards" id="cards"></div><div class="note">Uscita osservata ≠ vendita certa. La rotazione per tipologia è un proxy del mercato osservato, non una misura diretta della domanda acquirente.</div><div class="grid2"><div><h2>IMMOBILI DELLA ZONA</h2><div class="panel"><table><thead><tr><th>Via</th><th>Tipo</th><th>Prezzo</th><th>€/m²</th><th>Giorni</th><th>Stato</th><th>Agenzia</th><th>Fonte</th></tr></thead><tbody id="items"></tbody></table></div></div><div><h2>TIPOLOGIE NEL COMUNE</h2><div class="panel"><table><thead><tr><th>Tipologia</th><th>Stock</th><th>Uscite</th><th>Prezzo med.</th><th>€/m² med.</th><th>Permanenza</th><th>Ribasso</th></tr></thead><tbody id="types"></tbody></table></div></div></div><h2>AGENZIE — COME OPERANO</h2><div class="panel"><table><thead><tr><th>Agenzia</th><th>Stock</th><th>Nuovi 30g</th><th>Uscite 30g</th><th>Venduti conf.</th><th>Ribassi 30g</th><th>Giorni mercato</th><th>Primo ribasso</th><th>Ribasso medio</th><th>Score</th></tr></thead><tbody id="agencies"></tbody></table></div><h2>ULTIMI MOVIMENTI</h2><div class="panel"><table><thead><tr><th>Data</th><th>Via</th><th>Evento</th><th>Prima</th><th>Dopo</th><th>Agenzia</th></tr></thead><tbody id="events"></tbody></table></div><h2>SORGENTI GITHUB COLLEGATE</h2><div class="panel"><table><thead><tr><th>Repository</th><th>Modalità</th><th>Stato</th><th>Dataset</th><th>Record</th></tr></thead><tbody id="repos"></tbody></table></div></main><script>
const D={payload},sel=document.getElementById('comune');const esc=s=>String(s??'').replace(/[&<>\"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[m]));const n=x=>{{let v=Number(x);return Number.isFinite(v)?v:null}},f=x=>n(x)==null?'—':n(x).toLocaleString('it-IT',{{maximumFractionDigits:1}}),euro=x=>n(x)==null?'—':'€ '+n(x).toLocaleString('it-IT',{{maximumFractionDigits:0}});const med=a=>{{a=a.map(n).filter(x=>x!=null).sort((x,y)=>x-y);if(!a.length)return null;let m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2}},avg=a=>{{a=a.map(n).filter(x=>x!=null);return a.length?a.reduce((s,x)=>s+x,0)/a.length:null}};[...new Set(D.items.map(x=>x.comune).filter(Boolean))].sort().forEach(c=>{{let o=document.createElement('option');o.value=c;o.textContent=c;sel.appendChild(o)}});
function render(){{let c=sel.value.toLowerCase(),v=document.getElementById('via').value.trim().toLowerCase(),all=D.items.filter(x=>!c||(x.comune||'').toLowerCase()===c),items=all.filter(x=>!v||((x.via||'')+' '+(x.strada||'')).toLowerCase().includes(v)),active=items.filter(x=>x.attivo),cuts=items.reduce((s,x)=>s+(n(x.numero_ribassi)||0),0);document.getElementById('title').innerHTML=`<h2>${{esc(sel.value||'TUTTI I COMUNI')}}${{v?' — '+esc(document.getElementById('via').value):''}}</h2>`;document.getElementById('cards').innerHTML=`<div class='card'><small>Monitorati</small><b>${{items.length}}</b></div><div class='card'><small>Stock attivo</small><b>${{active.length}}</b></div><div class='card'><small>Prezzo mediano</small><b>${{euro(med(active.map(x=>x.prezzo)))}}</b></div><div class='card'><small>€/m² mediano</small><b>${{euro(med(active.map(x=>x.prezzo_mq)))}}</b></div><div class='card'><small>Permanenza media</small><b>${{f(avg(items.map(x=>x.giorni_mercato)))}} gg</b></div><div class='card'><small>Permanenza mediana</small><b>${{f(med(items.map(x=>x.giorni_mercato)))}} gg</b></div><div class='card'><small>Ribassi</small><b>${{f(cuts)}}</b></div><div class='card'><small>Venduti confermati</small><b>${{items.filter(x=>x.venduto_confermato).length}}</b></div>`;document.getElementById('items').innerHTML=items.slice(0,250).map(x=>`<tr><td><a href='${{esc(x.url||'#')}}' target='_blank'>${{esc(x.via||'DA VERIFICARE')}}</a></td><td>${{esc(x.tipologia||'—')}}</td><td>${{euro(x.prezzo)}}</td><td>${{euro(x.prezzo_mq)}}</td><td>${{f(x.giorni_mercato)}}</td><td>${{esc(x.stato||'—')}}</td><td>${{esc(x.agenzia||'—')}}</td><td>${{esc(x.fonte||x.origine||'—')}}</td></tr>`).join('')||'<tr><td colspan=8>Nessun immobile nel filtro</td></tr>';document.getElementById('types').innerHTML=D.tipi.filter(x=>!c||(x.COMUNE||'').toLowerCase()===c).sort((a,b)=>(n(b.STOCK_ATTIVO)||0)-(n(a.STOCK_ATTIVO)||0)).map(x=>`<tr><td>${{esc(x.TIPOLOGIA)}}</td><td>${{f(x.STOCK_ATTIVO)}}</td><td>${{f(x.USCITE_OSSERVATE)}}</td><td>${{euro(x.PREZZO_MEDIANO)}}</td><td>${{euro(x.PREZZO_MQ_MEDIANO)}}</td><td>${{f(x.PERMANENZA_MEDIANA_GG)}} gg</td><td>${{f(x.RIBASSO_MEDIO_PCT)}}%</td></tr>`).join('')||'<tr><td colspan=7>Nessun dato tipologia</td></tr>';document.getElementById('agencies').innerHTML=D.agenzie.filter(x=>!c||(x.COMUNI||'').toLowerCase().includes(c)).sort((a,b)=>(n(b.SCORE_OPERATIVO)||0)-(n(a.SCORE_OPERATIVO)||0)).slice(0,100).map(x=>`<tr><td>${{esc(x.AGENZIA)}}</td><td>${{f(x.STOCK_ATTIVO)}}</td><td>${{f(x.NUOVI_30G)}}</td><td>${{f(x.USCITE_OSSERVATE_30G)}}</td><td>${{f(x.VENDUTI_CONFERMATI)}}</td><td>${{f(x.RIBASSI_30G)}}</td><td>${{f(x.PERMANENZA_MEDIANA_GG)}}</td><td>${{f(x.GIORNI_MEDI_PRIMO_RIBASSO)}} gg</td><td>${{f(x.RIBASSO_MEDIO_PCT)}}%</td><td>${{f(x.SCORE_OPERATIVO)}}</td></tr>`).join('')||'<tr><td colspan=10>Nessuna agenzia identificata</td></tr>';document.getElementById('events').innerHTML=D.eventi.filter(x=>!c||(x.comune||'').toLowerCase()===c).filter(x=>!v||(x.via||'').toLowerCase().includes(v)).slice().reverse().slice(0,150).map(x=>`<tr><td>${{esc((x.data||'').slice(0,16).replace('T',' '))}}</td><td>${{esc(x.via||'—')}}</td><td>${{esc(x.evento||'—')}}</td><td>${{esc(x.valore_precedente||'—')}}</td><td>${{esc(x.valore_nuovo||'—')}}</td><td>${{esc(x.agenzia||'—')}}</td></tr>`).join('')||'<tr><td colspan=6>Nessun movimento</td></tr>';document.getElementById('repos').innerHTML=D.repos.map(x=>`<tr><td><a href='${{esc(x.url||'#')}}' target='_blank'>${{esc(x.name||x.repo)}}</a></td><td>${{esc(x.mode)}}</td><td class='${{x.status==='DATA_IMPORTED'||x.status==='CONNECTED_LINK'?'ok':'no'}}'>${{esc(x.status)}}</td><td>${{esc(x.file_found||'—')}}</td><td>${{f(x.rows_ingested)}}</td></tr>`).join('')||'<tr><td colspan=5>Nessuna sorgente esterna</td></tr>';}}sel.addEventListener('change',render);document.getElementById('via').addEventListener('input',render);render();
</script></body></html>'''
    OUT.write_text(page, encoding="utf-8")
    print(f"Brief appuntamento: {len(items)} immobili combinati")


if __name__ == "__main__":
    main()
