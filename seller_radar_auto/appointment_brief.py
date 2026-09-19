#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
INTEL = ROOT / "data" / "intelligence"
OUT = ROOT / "appointment_brief.html"
RADAR_STATUS = ROOT / "data" / "radar_run_status.json"
MARKET_STATUS = INTEL / "market_intelligence_status.json"
STATE = ROOT / "data" / "state.json"
ROME = ZoneInfo("Europe/Rome")


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


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


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
            key = "|".join([
                str(r.get("comune", "")).lower(), str(r.get("via", "")).lower(),
                str(r.get("prezzo", "")), str(r.get("tipologia", "")).lower()
            ])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main() -> None:
    items = dedupe(primary_items() + external_items())
    events_all = load_csv("eventi_mercato.csv")
    radar = load_json(RADAR_STATUS, {})
    market = load_json(MARKET_STATUS, {})
    state = load_json(STATE, {})
    comuni_rows = load_csv("kpi_comuni.csv")

    radar_fallback = state.get("matrix_discovery_updated_at", "")
    market_fallback = ""
    if comuni_rows:
        market_fallback = comuni_rows[0].get("ULTIMO_AGGIORNAMENTO", "")

    now = datetime.now(timezone.utc)
    meta = {
        "radar_status": radar.get("status", "LEGACY_NO_RUN_MARKER"),
        "data_refresh_completed_at": radar.get("data_refresh_completed_at_rome")
            or radar.get("data_refresh_completed_at_utc")
            or radar_fallback,
        "radar_run_id": radar.get("radar_run_id", ""),
        "radar_source_sha": radar.get("source_sha", ""),
        "state_sha256": radar.get("state_sha256", ""),
        "work_queue_sha256": radar.get("work_queue_sha256", ""),
        "market_intelligence_completed_at": market.get("market_intelligence_completed_at_rome")
            or market.get("market_intelligence_completed_at_utc")
            or market_fallback,
        "brief_generated_at": now.astimezone(ROME).isoformat(timespec="seconds"),
    }
    quality = {
        "totale": len(items),
        "indirizzo": sum(bool((x.get("via") or x.get("strada") or "").strip()) for x in items),
        "prezzo": sum(x.get("prezzo") is not None for x in items),
        "prezzo_mq": sum(x.get("prezzo_mq") is not None for x in items),
        "agenzia": sum(bool((x.get("agenzia") or "").strip()) for x in items),
        "url": sum(bool((x.get("url") or "").strip()) for x in items),
    }
    data = {
        "items": items,
        "tipi": load_csv("kpi_tipologie.csv"),
        "agenzie": load_csv("kpi_agenzie.csv"),
        "eventi": events_all[-800:],
        "eventi_totali": len(events_all),
        "repos": load_csv("repo_status.csv"),
        "meta": meta,
        "quality": quality,
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = r'''<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>F1 Brief Appuntamento</title>
<style>
:root{--g:#39F28A;--bg:#070907;--p:#101510;--p2:#141b16;--line:#2b372e;--mut:#aeb7b0;--warn:#ffd166;--bad:#ff7b7b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:#fff;font-family:Arial,sans-serif;line-height:1.35}
header{padding:18px;border-bottom:1px solid var(--line);position:sticky;top:0;background:#070907f2;z-index:5}
h1{margin:0;font-size:22px} header p{margin:4px 0;color:var(--mut)}
main{max-width:1450px;margin:auto;padding:16px}
.filters{display:grid;grid-template-columns:1fr 1fr auto;gap:9px}
select,input,button{padding:12px;border-radius:10px;border:1px solid var(--line);background:#111713;color:#fff}
button{background:var(--g);color:#07100a;font-weight:900;cursor:pointer}
.status-grid,.cards,.quality{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:9px;margin:14px 0}
.card,.panel,.status{background:var(--p);border:1px solid var(--line);border-radius:12px;padding:12px}
.card small,.status small{display:block;color:var(--mut);font-size:9px;text-transform:uppercase;letter-spacing:.04em}
.card b,.status b{font-size:20px}.sub{display:block;color:var(--mut);font-size:10px;margin-top:4px}
.status.good{border-color:#2f8150}.status.warn{border-color:#8a6b28}.status.bad{border-color:#8b3d3d}
h2{font-size:15px;color:var(--g);margin:22px 0 8px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.panel{overflow:auto} table{width:100%;border-collapse:collapse;min-width:720px}
th,td{padding:8px;border-bottom:1px solid var(--line);font-size:11px;text-align:left;vertical-align:top}
th{color:var(--mut);background:var(--p2);position:sticky;top:0}
a{color:var(--g)}.note{font-size:11px;color:var(--warn);margin:10px 0}.muted{color:var(--mut)}
.ok{color:var(--g)}.no{color:var(--warn)}.danger{color:var(--bad)}
.badge{display:inline-block;padding:3px 7px;border:1px solid var(--line);border-radius:999px;font-size:9px;white-space:nowrap}
.quality .card b{font-size:17px}.screen-only{display:block}
@media(max-width:800px){.filters,.grid2{grid-template-columns:1fr}.status-grid,.cards,.quality{grid-template-columns:repeat(2,minmax(0,1fr))}header{position:static}main{padding:10px}.panel{border-radius:9px}}
@media(max-width:430px){.status-grid,.cards,.quality{grid-template-columns:1fr 1fr}.card,.status{padding:10px}.card b,.status b{font-size:17px}}
@page{size:A4 landscape;margin:10mm}
@media print{
  body{background:#fff;color:#111;font-size:9pt}header{position:static;background:#fff;border-bottom:2px solid #111;padding:0 0 8mm}
  header p,.muted{color:#444}.filters,.screen-only,button{display:none!important}main{max-width:none;padding:0}
  .panel,.card,.status{background:#fff;border-color:#bbb;break-inside:avoid}.grid2{display:block}
  h2{color:#111;break-after:avoid}.cards,.status-grid,.quality{break-inside:avoid}
  table{min-width:0;font-size:8pt}th,td{font-size:8pt;padding:4px;color:#111}th{background:#eee;position:static}
  a{color:#111;text-decoration:none}.note{color:#333}
}
</style>
</head>
<body>
<header>
  <h1>F1 IMMOBILIARE — BRIEF APPUNTAMENTO</h1>
  <p>Comune → via → prezzi → permanenza osservata → ribassi → tipologie → agenzie → movimenti</p>
</header>
<main>
  <div class="filters">
    <select id="comune"><option value="">Seleziona Comune</option></select>
    <input id="via" placeholder="Via / borgata / località">
    <button onclick="window.print()">STAMPA / SALVA PDF</button>
  </div>

  <div class="status-grid" id="status"></div>
  <div id="title"></div>
  <div class="cards" id="cards"></div>

  <div class="note">Uscita osservata ≠ vendita. “Vendita segnalata dalla fonte” indica un segnale presente nell’annuncio o nella fonte e non una verifica notarile. “Permanenza osservata” misura il periodo visto da Seller Radar, non necessariamente i giorni reali dalla prima pubblicazione.</div>

  <div class="grid2">
    <div>
      <h2>IMMOBILI DELLA ZONA</h2>
      <div class="panel"><table>
        <thead><tr><th>Via</th><th>Tipo</th><th>Prezzo</th><th>€/m²</th><th>Giorni osservati</th><th>Stato</th><th>Agenzia</th><th>Fonte</th></tr></thead>
        <tbody id="items"></tbody>
      </table></div>
    </div>
    <div>
      <h2>TIPOLOGIE NEL COMUNE</h2>
      <div class="panel"><table>
        <thead><tr><th>Tipologia</th><th>Stock</th><th>Uscite</th><th>Prezzo mediano</th><th>€/m² mediano</th><th>Permanenza osservata</th><th>Ribasso medio</th></tr></thead>
        <tbody id="types"></tbody>
      </table></div>
    </div>
  </div>

  <h2>AGENZIE — ATTIVITÀ OSSERVATA</h2>
  <div class="note">L’indice attività osservata è uno score euristico sul dinamismo degli annunci; non misura qualità, fatturato, rogiti o conversion rate.</div>
  <div class="panel"><table>
    <thead><tr><th>Agenzia</th><th>Stock</th><th>Nuovi 30g</th><th>Uscite 30g</th><th>Vendite segnalate</th><th>Ribassi 30g</th><th>Permanenza osservata</th><th>Primo ribasso</th><th>Ribasso medio</th><th>Indice attività osservata</th></tr></thead>
    <tbody id="agencies"></tbody>
  </table></div>

  <h2>ULTIMI MOVIMENTI</h2>
  <p class="muted" id="event-meta"></p>
  <div class="panel"><table>
    <thead><tr><th>Data</th><th>Via</th><th>Evento</th><th>Prima</th><th>Dopo</th><th>Agenzia</th></tr></thead>
    <tbody id="events"></tbody>
  </table></div>

  <h2>QUALITÀ DATI</h2>
  <div class="quality" id="quality"></div>

  <h2>SORGENTI GITHUB COLLEGATE</h2>
  <div class="panel"><table>
    <thead><tr><th>Repository</th><th>Modalità</th><th>Stato effettivo</th><th>Dataset</th><th>Record importati</th></tr></thead>
    <tbody id="repos"></tbody>
  </table></div>

  <p class="note">I dati derivano da osservazioni di fonti web pubbliche e dalla cronologia Seller Radar. Sono utilizzati per market intelligence e preparazione commerciale; non costituiscono certificazione catastale, notarile o dello stato effettivo di vendita.</p>
</main>

<script>
const D=__PAYLOAD__;
const sel=document.getElementById("comune");
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
const n=x=>{let v=Number(x);return Number.isFinite(v)?v:null};
const f=x=>n(x)==null?"—":n(x).toLocaleString("it-IT",{maximumFractionDigits:1});
const euro=x=>n(x)==null?"—":"€ "+n(x).toLocaleString("it-IT",{maximumFractionDigits:0});
const med=a=>{a=a.map(n).filter(x=>x!=null).sort((x,y)=>x-y);if(!a.length)return null;let m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2};
const avg=a=>{a=a.map(n).filter(x=>x!=null);return a.length?a.reduce((s,x)=>s+x,0)/a.length:null};
const norm=s=>String(s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/[.,'’/\\-]+/g," ").replace(/\bc so\b/g,"corso").replace(/\bv le\b/g,"viale").replace(/\bp za\b/g,"piazza").replace(/\s+/g," ").trim();
const pct=(a,b)=>b?((a/b)*100).toLocaleString("it-IT",{maximumFractionDigits:1})+"%":"—";
const fmtDate=s=>{if(!s)return"Non disponibile";let d=new Date(s);return isNaN(d)?"Non disponibile":d.toLocaleString("it-IT",{dateStyle:"short",timeStyle:"short"})};
const sample=t=>"<span class='sub'>Campione: "+t+"</span>";
const valid=x=>x!==null&&x!==undefined&&x!=="";

[...new Set(D.items.map(x=>x.comune).filter(Boolean))].sort().forEach(c=>{
  let o=document.createElement("option");o.value=c;o.textContent=c;sel.appendChild(o)
});

function freshness(){
  const s=D.meta.data_refresh_completed_at;
  if(!s)return {label:"FRESCHEZZA NON DISPONIBILE",cls:"warn",detail:"Nessun timestamp di raccolta affidabile"};
  const d=new Date(s);if(isNaN(d))return {label:"FRESCHEZZA NON DISPONIBILE",cls:"warn",detail:s};
  const hours=Math.max(0,(Date.now()-d.getTime())/3600000);
  if(hours<=24)return {label:"DATI AGGIORNATI",cls:"good",detail:"Ultima raccolta "+hours.toLocaleString("it-IT",{maximumFractionDigits:1})+" ore fa"};
  if(hours<=48)return {label:"DATI DA RICONTROLLARE",cls:"warn",detail:"Ultima raccolta "+hours.toLocaleString("it-IT",{maximumFractionDigits:1})+" ore fa"};
  return {label:"DATI OBSOLETI",cls:"bad",detail:"Ultima raccolta "+hours.toLocaleString("it-IT",{maximumFractionDigits:1})+" ore fa"};
}

function renderStatus(){
  const fr=freshness();
  document.getElementById("status").innerHTML=
    "<div class='status "+fr.cls+"'><small>Stato freschezza</small><b>"+esc(fr.label)+"</b><span class='sub'>"+esc(fr.detail)+"</span></div>"+
    "<div class='status'><small>Ultima raccolta dati</small><b>"+esc(fmtDate(D.meta.data_refresh_completed_at))+"</b><span class='sub'>Run "+esc(D.meta.radar_run_id||"legacy/non disponibile")+"</span></div>"+
    "<div class='status'><small>Market Intelligence</small><b>"+esc(fmtDate(D.meta.market_intelligence_completed_at))+"</b><span class='sub'>Ricalcolo KPI</span></div>"+
    "<div class='status'><small>Brief generato</small><b>"+esc(fmtDate(D.meta.brief_generated_at))+"</b><span class='sub'>Generazione pagina</span></div>";
}

function renderQuality(){
  const q=D.quality,total=q.totale||0;
  const rows=[
    ["Schede totali",total,total],
    ["Con indirizzo",q.indirizzo,total],
    ["Con prezzo",q.prezzo,total],
    ["Con €/m²",q.prezzo_mq,total],
    ["Con agenzia identificata",q.agenzia,total],
    ["Con URL fonte",q.url,total]
  ];
  document.getElementById("quality").innerHTML=rows.map(r=>
    "<div class='card'><small>"+esc(r[0])+"</small><b>"+f(r[1])+" / "+f(r[2])+"</b><span class='sub'>"+pct(r[1],r[2])+"</span></div>"
  ).join("");
}

function render(){
  let c=norm(sel.value),rawVia=document.getElementById("via").value,v=norm(rawVia);
  let all=D.items.filter(x=>!c||norm(x.comune)===c);
  let items=all.filter(x=>!v||norm((x.via||"")+" "+(x.strada||"")).includes(v));
  let active=items.filter(x=>x.attivo);
  let priceVals=active.filter(x=>valid(x.prezzo)).map(x=>x.prezzo);
  let psmVals=active.filter(x=>valid(x.prezzo_mq)).map(x=>x.prezzo_mq);
  let domVals=items.filter(x=>valid(x.giorni_mercato)).map(x=>x.giorni_mercato);
  let cutItems=items.filter(x=>(n(x.numero_ribassi)||0)>0);
  let cutPct=cutItems.filter(x=>valid(x.ribasso_totale_pct)).map(x=>x.ribasso_totale_pct);
  let cuts=items.reduce((s,x)=>s+(n(x.numero_ribassi)||0),0);
  let sold=items.filter(x=>x.venduto_confermato).length;

  document.getElementById("title").innerHTML="<h2>"+esc(sel.value||"TUTTI I COMUNI")+(v?" — "+esc(rawVia):"")+"</h2>";
  document.getElementById("cards").innerHTML=
    "<div class='card'><small>Monitorati</small><b>"+items.length+"</b>"+sample(items.length+" schede")+"</div>"+
    "<div class='card'><small>Stock attivo</small><b>"+active.length+"</b>"+sample(items.length+" schede")+"</div>"+
    "<div class='card'><small>Prezzo mediano</small><b>"+euro(med(priceVals))+"</b>"+sample(priceVals.length+" immobili")+"</div>"+
    "<div class='card'><small>€/m² mediano</small><b>"+euro(med(psmVals))+"</b>"+sample(psmVals.length+" immobili")+"</div>"+
    "<div class='card'><small>Permanenza osservata mediana</small><b>"+f(med(domVals))+" gg</b>"+sample(domVals.length+" immobili")+"</div>"+
    "<div class='card'><small>Ribassi rilevati</small><b>"+f(cuts)+"</b>"+sample(cutItems.length+" immobili con ribasso")+"</div>"+
    "<div class='card'><small>Ribasso medio</small><b>"+f(avg(cutPct))+"%</b>"+sample(cutPct.length+" immobili")+"</div>"+
    "<div class='card'><small>Vendite segnalate dalla fonte</small><b>"+sold+"</b>"+sample(items.length+" schede")+"</div>";

  document.getElementById("items").innerHTML=items.slice(0,250).map(x=>{
    const via=esc(x.via||x.strada||"DA VERIFICARE");
    const link=x.url?"<a href='"+esc(x.url)+"' target='_blank' rel='noopener noreferrer'>"+via+"</a>":via;
    return "<tr><td>"+link+"</td><td>"+esc(x.tipologia||"—")+"</td><td>"+euro(x.prezzo)+"</td><td>"+euro(x.prezzo_mq)+"</td><td>"+f(x.giorni_mercato)+"</td><td>"+esc(x.stato||"—")+"</td><td>"+esc(x.agenzia||"—")+"</td><td>"+esc(x.fonte||x.origine||"—")+"</td></tr>";
  }).join("")||"<tr><td colspan='8'>Nessun immobile nel filtro</td></tr>";

  const typeRows=D.tipi.filter(x=>!c||norm(x.COMUNE)===c).sort((a,b)=>(n(b.STOCK_ATTIVO)||0)-(n(a.STOCK_ATTIVO)||0));
  document.getElementById("types").innerHTML=typeRows.map(x=>{
    const tri=all.filter(r=>norm(r.tipologia)===norm(x.TIPOLOGIA));
    const ta=tri.filter(r=>r.attivo);
    const cp=ta.filter(r=>valid(r.prezzo)).length;
    const cm=ta.filter(r=>valid(r.prezzo_mq)).length;
    const cd=tri.filter(r=>valid(r.giorni_mercato)).length;
    const cr=tri.filter(r=>(n(r.numero_ribassi)||0)>0).length;
    return "<tr><td>"+esc(x.TIPOLOGIA)+"</td><td>"+f(x.STOCK_ATTIVO)+"</td><td>"+f(x.USCITE_OSSERVATE)+"</td><td>"+euro(x.PREZZO_MEDIANO)+sample(cp)+"</td><td>"+euro(x.PREZZO_MQ_MEDIANO)+sample(cm)+"</td><td>"+f(x.PERMANENZA_MEDIANA_GG)+" gg"+sample(cd)+"</td><td>"+f(x.RIBASSO_MEDIO_PCT)+"%"+sample(cr)+"</td></tr>";
  }).join("")||"<tr><td colspan='7'>Nessun dato tipologia</td></tr>";

  document.getElementById("agencies").innerHTML=D.agenzie.filter(x=>!c||norm(x.COMUNI).includes(c)).sort((a,b)=>(n(b.SCORE_OPERATIVO)||0)-(n(a.SCORE_OPERATIVO)||0)).slice(0,100).map(x=>
    "<tr><td>"+esc(x.AGENZIA)+"</td><td>"+f(x.STOCK_ATTIVO)+"</td><td>"+f(x.NUOVI_30G)+"</td><td>"+f(x.USCITE_OSSERVATE_30G)+"</td><td>"+f(x.VENDUTI_CONFERMATI)+"</td><td>"+f(x.RIBASSI_30G)+"</td><td>"+f(x.PERMANENZA_MEDIANA_GG)+" gg</td><td>"+f(x.GIORNI_MEDI_PRIMO_RIBASSO)+" gg</td><td>"+f(x.RIBASSO_MEDIO_PCT)+"%</td><td>"+f(x.SCORE_OPERATIVO)+"</td></tr>"
  ).join("")||"<tr><td colspan='10'>Nessuna agenzia identificata</td></tr>";

  const ev=D.eventi.filter(x=>!c||norm(x.comune)===c).filter(x=>!v||norm(x.via).includes(v)).slice().reverse().slice(0,150);
  document.getElementById("events").innerHTML=ev.map(x=>
    "<tr><td>"+esc((x.data||"").slice(0,16).replace("T"," "))+"</td><td>"+esc(x.via||"—")+"</td><td>"+esc(x.evento||"—")+"</td><td>"+esc(x.valore_precedente||"—")+"</td><td>"+esc(x.valore_nuovo||"—")+"</td><td>"+esc(x.agenzia||"—")+"</td></tr>"
  ).join("")||"<tr><td colspan='6'>Nessun movimento</td></tr>";
  document.getElementById("event-meta").textContent="Ultimi movimenti caricati nel Brief: "+D.eventi.length+" su "+D.eventi_totali+" eventi storici disponibili; visualizzati al massimo 150 per il filtro corrente.";

  document.getElementById("repos").innerHTML=D.repos.map(x=>{
    let label=x.status;
    if(x.mode==="LINK_ONLY")label="CONNESSO — SOLO LINK";
    else if(x.status==="DATA_IMPORTED")label="DATI IMMOBILIARI IMPORTATI";
    else if(x.status==="NO_DATA")label="NESSUN DATASET IMPORTATO";
    const repo=x.url?"<a href='"+esc(x.url)+"' target='_blank' rel='noopener noreferrer'>"+esc(x.name||x.repo)+"</a>":esc(x.name||x.repo);
    return "<tr><td>"+repo+"</td><td>"+esc(x.mode||"—")+"</td><td>"+esc(label||"—")+"</td><td>"+esc(x.file_found||"—")+"</td><td>"+f(x.rows_ingested)+"</td></tr>";
  }).join("")||"<tr><td colspan='5'>Nessuna sorgente esterna</td></tr>";
}

sel.addEventListener("change",render);
document.getElementById("via").addEventListener("input",render);
renderStatus();
renderQuality();
render();
</script>
</body>
</html>'''.replace("__PAYLOAD__", payload)

    OUT.write_text(page, encoding="utf-8")
    print("Brief appuntamento: %d immobili combinati, %d eventi incorporati su %d storici" % (len(items), len(data["eventi"]), len(events_all)))


if __name__ == "__main__":
    main()
