#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 Centrale Telefonate Guidate — unico punto di partenza delle chiamate.

Unisce sul PC:
1) contatti pubblici incrociati con microzone/Radar;
2) prospect web pubblici Susa 20 km, comprese attività e professionisti.

La lista NON è un CRM. Un contatto passa al CRM solo dopo un esito utile.
Nessun telefono/email viene pubblicato su GitHub.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from pathlib import Path

BASE = Path.home() / "Documents" / "F1_Directory_Microzone"
DATA = BASE / "data"
MICRO = DATA / "telefonate_susa_20km.csv"
WEB = DATA / "prospect_web_susa_20km.csv"
OUT_CSV = DATA / "centrale_telefonate_guidate.csv"
OUT_HTML = BASE / "F1_CENTRALE_TELEFONATE_GUIDATE.html"

CRM_URL = "http://127.0.0.1:4173/"
SCRIPT_URL = "https://f1immobiliare.com/pages/acquisizione-immobiliare"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def digits(value: str) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def safe_url(value: str) -> str:
    value = str(value or "").strip()
    return value if value.startswith(("http://", "https://")) else ""


def intval(value, default=0):
    try:
        return int(float(str(value or default).replace(",", ".")))
    except Exception:
        return default


def first(row: dict, *names: str) -> str:
    for name in names:
        value = str(row.get(name) or "").strip()
        if value:
            return value
    return ""


def from_micro(row: dict) -> dict:
    phone = digits(row.get("TELEFONO") or "")
    town = first(row, "COMUNE", "RADAR_COMUNE")
    name = first(row, "NOME") or "Contatto pubblico microzona"
    radar_type = first(row, "RADAR_TIPO_OPPORTUNITA", "RADAR_SELLER_SIGNAL", "RADAR_INDIZIO_INSERZIONISTA")
    title = first(row, "RADAR_TITOLO", "RADAR_COSA_CERCO", "RIFERIMENTO_ANNUNCIO")
    street = first(row, "VIA_TARGET", "VIA_CONTATTO", "RADAR_DOVE_ANDRE")
    objective = first(row, "RADAR_OBIETTIVO_COMMERCIALE")
    reason_bits = [x for x in [objective, radar_type, title, street] if x]
    reason = " · ".join(reason_bits[:4]) or "Contatto pubblico nella microzona collegata a un segnale Radar"
    score = intval(first(row, "RADAR_SCORE", "SCORE"), 45)
    cid = hashlib.sha256(f"micro|{town}|{phone}|{street}".encode("utf-8")).hexdigest()[:20]
    return {
        "ID": cid,
        "SCORE": max(score, 45),
        "COMUNE": town,
        "NOME": name,
        "CATEGORIA": "MICROZONA_RADAR",
        "TELEFONO": phone,
        "EMAIL": "",
        "MOTIVO_CONTATTO": reason,
        "SEGNALE_RADAR": radar_type,
        "RADAR_SCORE": score,
        "RADAR_URL": safe_url(first(row, "RADAR_URL", "ANNUNCIO_URL")),
        "FONTE_CONTATTO": first(row, "FONTE_CONTATTO"),
        "URL_CONTATTO": safe_url(first(row, "URL_CONTATTO")),
        "ORIGINE": "RADAR + MICROZONA",
        "RPO_STATUS": first(row, "RPO_STATUS") or "DA_VERIFICARE_PRIMA_DEL_CONTATTO",
        "STATO": "DA_CONTATTARE",
    }


def from_web(row: dict) -> dict:
    cid = first(row, "PROSPECT_ID") or hashlib.sha256(
        f"web|{row.get('COMUNE','')}|{row.get('TELEFONO','')}|{row.get('EMAIL','')}".encode("utf-8")
    ).hexdigest()[:20]
    return {
        "ID": cid,
        "SCORE": intval(row.get("SCORE"), 35),
        "COMUNE": first(row, "COMUNE"),
        "NOME": first(row, "NOME") or "Prospect pubblico",
        "CATEGORIA": first(row, "CATEGORIA") or "PROSPECT_WEB",
        "TELEFONO": digits(row.get("TELEFONO") or ""),
        "EMAIL": first(row, "EMAIL"),
        "MOTIVO_CONTATTO": first(row, "MOTIVO_CONTATTO"),
        "SEGNALE_RADAR": first(row, "SEGNALE_RADAR"),
        "RADAR_SCORE": intval(row.get("RADAR_SCORE"), 0),
        "RADAR_URL": safe_url(first(row, "RADAR_URL")),
        "FONTE_CONTATTO": first(row, "FONTE_CONTATTO"),
        "URL_CONTATTO": safe_url(first(row, "URL_CONTATTO")),
        "ORIGINE": "PROSPECT WEB PUBBLICO",
        "RPO_STATUS": first(row, "RPO_STATUS") or "DA_VERIFICARE_PRIMA_DEL_CONTATTO",
        "STATO": "DA_CONTATTARE",
    }


def merge_rows(rows: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in rows:
        phone = digits(row.get("TELEFONO") or "")
        email = str(row.get("EMAIL") or "").casefold().strip()
        key = ("p:" + phone) if phone else (("e:" + email) if email else "id:" + row["ID"])
        if key not in merged:
            merged[key] = row
            continue
        cur = merged[key]
        if intval(row.get("SCORE")) > intval(cur.get("SCORE")):
            keep, other = row, cur
        else:
            keep, other = cur, row
        for field in ("EMAIL", "TELEFONO", "RADAR_URL", "URL_CONTATTO", "SEGNALE_RADAR", "FONTE_CONTATTO"):
            if not keep.get(field) and other.get(field):
                keep[field] = other[field]
        reasons = []
        for value in (keep.get("MOTIVO_CONTATTO"), other.get("MOTIVO_CONTATTO")):
            value = str(value or "").strip()
            if value and value not in reasons:
                reasons.append(value)
        keep["MOTIVO_CONTATTO"] = " | ".join(reasons)[:600]
        origins = sorted(set((str(keep.get("ORIGINE") or "") + " + " + str(other.get("ORIGINE") or "")).split(" + ")))
        keep["ORIGINE"] = " + ".join(x for x in origins if x)
        merged[key] = keep
    out = [r for r in merged.values() if r.get("TELEFONO") or r.get("EMAIL")]
    return sorted(out, key=lambda r: (-intval(r.get("SCORE")), r.get("COMUNE", ""), r.get("NOME", "").casefold()))


def esc(value) -> str:
    return html.escape(str(value or ""))


def js(value) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def render(rows: list[dict]) -> None:
    fields = [
        "ID", "SCORE", "COMUNE", "NOME", "CATEGORIA", "TELEFONO", "EMAIL",
        "MOTIVO_CONTATTO", "SEGNALE_RADAR", "RADAR_SCORE", "RADAR_URL",
        "FONTE_CONTATTO", "URL_CONTATTO", "ORIGINE", "RPO_STATUS", "STATO",
    ]
    DATA.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    page = f"""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><meta name='robots' content='noindex,nofollow,noarchive'><title>F1 Centrale Telefonate Guidate</title><style>
:root{{--bg:#070907;--p:#101510;--p2:#171d18;--line:#2a342c;--txt:#fff;--mut:#aeb7b0;--g:#39f28a;--gold:#f4c95d;--red:#ff7777}}*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(180deg,#050705,#0b110c);color:var(--txt);font-family:Arial,sans-serif}}header{{position:sticky;top:0;z-index:5;background:#070907f5;border-bottom:1px solid var(--line);padding:13px}}.head{{max-width:1180px;margin:auto}}.ey{{color:var(--g);font-size:10px;font-weight:900;letter-spacing:.15em}}h1{{margin:4px 0;font-size:clamp(25px,5vw,40px)}}.sub{{color:var(--mut);font-size:12px;line-height:1.45}}main{{max-width:1180px;margin:auto;padding:14px 12px 80px}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:12px 0}}.stat{{background:var(--p);border:1px solid var(--line);border-radius:12px;padding:10px;text-align:center;font-size:10px}}.stat b{{display:block;color:var(--g);font-size:22px}}.filters{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:8px;margin:12px 0}}input,select{{width:100%;padding:11px;border-radius:9px;border:1px solid var(--line);background:#0e140f;color:#fff}}.card{{background:var(--p);border:1px solid var(--line);border-radius:15px;padding:14px;margin:10px 0}}.top{{display:flex;justify-content:space-between;gap:10px}}.name{{font-size:17px;font-weight:900}}.town{{color:var(--g);font-size:11px;font-weight:900}}.score{{border:1px solid #35513d;color:var(--g);border-radius:999px;padding:6px 8px;height:max-content;font-size:10px;font-weight:900}}.meta{{color:var(--mut);font-size:11px;line-height:1.45;margin-top:5px}}.reason{{margin-top:9px;padding:10px;border-left:3px solid var(--g);background:#0d130e;font-size:12px;line-height:1.45}}.contacts{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}}.contact{{font-size:13px;font-weight:900}}.actions{{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}}.btn{{display:inline-flex;align-items:center;justify-content:center;padding:9px 11px;border-radius:8px;border:1px solid var(--line);background:#18201a;color:#fff;text-decoration:none;font-size:10px;font-weight:900;cursor:pointer}}.btn.primary{{background:var(--g);color:#07100a;border-color:var(--g)}}.btn.gold{{color:var(--gold);border-color:#66552a;background:#241f12}}.btn.disabled{{opacity:.35;pointer-events:none}}.verify{{margin-top:10px;font-size:10px;color:var(--gold)}}.verify input{{width:auto}}.outcome{{margin-top:10px;display:grid;grid-template-columns:1fr auto;gap:8px}}.crm{{display:none}}.crm.show{{display:inline-flex}}.empty{{padding:30px;text-align:center;color:var(--mut)}}.rule{{padding:12px;border:1px solid #5d512d;background:#1d190d;border-radius:12px;color:#f1dda2;font-size:11px;line-height:1.5;margin:12px 0}}@media(max-width:700px){{.stats{{grid-template-columns:1fr 1fr}}.filters{{grid-template-columns:1fr}}.top{{display:block}}.score{{display:inline-block;margin-top:7px}}.actions .btn{{flex:1}}.outcome{{grid-template-columns:1fr}}}}</style></head><body><header><div class='head'><div class='ey'>F1 IMMOBILIARE · SUSA 20 KM</div><h1>F1 CENTRALE TELEFONATE GUIDATE</h1><div class='sub'>Unica postazione chiamate. Prospect pubblici + microzone Radar + attività/professionisti. Il CRM entra solo dopo un esito utile.</div></div></header><main><div class='rule'><b>CONTROLLO PRIMA DI CHIAMARE:</b> la presenza pubblica di un numero/email non dimostra proprietà immobiliare né rende automaticamente lecito qualunque contatto commerciale. Verifica fonte, pertinenza e regole RPO/privacy applicabili. Non usare dati da aree riservate.</div><div class='stats'><div class='stat'><b id='tot'>0</b>da lavorare</div><div class='stat'><b id='phones'>0</b>con telefono</div><div class='stat'><b id='emails'>0</b>con email</div><div class='stat'><b id='radar'>0</b>incrocio Radar</div></div><div class='filters'><input id='q' placeholder='Cerca nome, comune, motivo...'><select id='town'><option value=''>Tutti i comuni</option></select><select id='status'><option value=''>Tutti gli stati</option><option>DA CONTATTARE</option><option>NON RISPONDE</option><option>RICHIAMARE</option><option>POSSIBILE IMMOBILE</option><option>SEGNALAZIONE</option><option>APPUNTAMENTO</option><option>NON INTERESSATO</option></select></div><div id='list'></div></main><script>const DATA={payload};const SCRIPT={js(SCRIPT_URL)};const CRM={js(CRM_URL)};const STORE='f1:centrale-telefonate-guidate:v1:';function esc(s){{return String(s||'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]))}}function st(id){{try{{return JSON.parse(localStorage.getItem(STORE+id)||'{{}}')}}catch(e){{return {{}}}}}}function save(id,x){{localStorage.setItem(STORE+id,JSON.stringify(x))}}function dial(p){{p=String(p||'').replace(/\D/g,'');return p?('tel:+39'+p):''}}function stateOf(r){{return st(r.ID).outcome||'DA CONTATTARE'}}function verified(r){{return !!st(r.ID).verified}}function render(){{let query=q.value.trim().toLowerCase(),t=town.value,s=status.value;let rows=DATA.filter(r=>{{let state=stateOf(r),hay=[r.NOME,r.COMUNE,r.CATEGORIA,r.MOTIVO_CONTATTO,r.SEGNALE_RADAR,r.TELEFONO,r.EMAIL].join(' ').toLowerCase();return(!query||hay.includes(query))&&(!t||r.COMUNE===t)&&(!s||state===s)}});tot.textContent=rows.length;phones.textContent=rows.filter(r=>r.TELEFONO).length;emails.textContent=rows.filter(r=>r.EMAIL).length;radar.textContent=rows.filter(r=>r.SEGNALE_RADAR||r.RADAR_URL||r.ORIGINE.includes('RADAR')).length;list.innerHTML=rows.length?rows.map(r=>{{let x=st(r.ID),ok=!!x.verified,state=x.outcome||'DA CONTATTARE',positive=['POSSIBILE IMMOBILE','SEGNALAZIONE','APPUNTAMENTO'].includes(state),call=r.TELEFONO?`<a class="btn primary ${{ok?'':'disabled'}}" data-call="${{esc(r.ID)}}" href="${{ok?dial(r.TELEFONO):'#'}}">CHIAMA</a>`:'',mail=r.EMAIL?`<a class="btn ${{ok?'':'disabled'}}" href="${{ok?'mailto:'+encodeURIComponent(r.EMAIL):'#'}}">EMAIL</a>`:'',source=r.URL_CONTATTO?`<a class="btn" target="_blank" rel="noopener" href="${{esc(r.URL_CONTATTO)}}">FONTE CONTATTO</a>`:'',rad=r.RADAR_URL?`<a class="btn" target="_blank" rel="noopener" href="${{esc(r.RADAR_URL)}}">FONTE RADAR</a>`:'';return `<article class="card"><div class="top"><div><div class="town">${{esc(r.COMUNE)}} · ${{esc(r.CATEGORIA)}}</div><div class="name">${{esc(r.NOME)}}</div><div class="meta">${{esc(r.ORIGINE)}}${{r.FONTE_CONTATTO?' · '+esc(r.FONTE_CONTATTO):''}}</div></div><span class="score">SCORE ${{esc(r.SCORE)}}</span></div><div class="reason"><b>PERCHÉ LO CHIAMO</b><br>${{esc(r.MOTIVO_CONTATTO||'Prospect da qualificare')}}</div><div class="contacts">${{r.TELEFONO?'<span class="contact">☎ '+esc(r.TELEFONO)+'</span>':''}}${{r.EMAIL?'<span class="contact">✉ '+esc(r.EMAIL)+'</span>':''}}</div><label class="verify"><input type="checkbox" data-verify="${{esc(r.ID)}}" ${{ok?'checked':''}}> HO VERIFICATO FONTE PUBBLICA / PERTINENZA DEL CONTATTO</label><div class="actions">${{call}}${{mail}}${{source}}${{rad}}<a class="btn gold" target="_blank" rel="noopener" href="${{SCRIPT}}">SCRIPT F1</a></div><div class="outcome"><select data-outcome="${{esc(r.ID)}}"><option ${{state==='DA CONTATTARE'?'selected':''}}>DA CONTATTARE</option><option ${{state==='NON RISPONDE'?'selected':''}}>NON RISPONDE</option><option ${{state==='RICHIAMARE'?'selected':''}}>RICHIAMARE</option><option ${{state==='POSSIBILE IMMOBILE'?'selected':''}}>POSSIBILE IMMOBILE</option><option ${{state==='SEGNALAZIONE'?'selected':''}}>SEGNALAZIONE</option><option ${{state==='APPUNTAMENTO'?'selected':''}}>APPUNTAMENTO</option><option ${{state==='NON INTERESSATO'?'selected':''}}>NON INTERESSATO</option></select><a class="btn primary crm ${{positive?'show':''}}" target="_blank" href="${{CRM}}">PASSA AL CRM</a></div></article>`}}).join(''):'<div class="empty">Nessun contatto con questi filtri.</div>';bind()}}function bind(){{document.querySelectorAll('[data-verify]').forEach(el=>el.onchange=()=>{{let x=st(el.dataset.verify);x.verified=el.checked;save(el.dataset.verify,x);render()}});document.querySelectorAll('[data-outcome]').forEach(el=>el.onchange=()=>{{let x=st(el.dataset.outcome);x.outcome=el.value;save(el.dataset.outcome,x);render()}})}}let towns=[...new Set(DATA.map(r=>r.COMUNE).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'it'));town.innerHTML='<option value="">Tutti i comuni</option>'+towns.map(x=>`<option>${{esc(x)}}</option>`).join('');q.oninput=town.onchange=status.onchange=render;render();</script></body></html>"""
    OUT_HTML.write_text(page, encoding="utf-8")


def main() -> int:
    micro = [from_micro(r) for r in read_csv(MICRO) if digits(r.get("TELEFONO") or "")]
    web = [from_web(r) for r in read_csv(WEB) if r.get("TELEFONO") or r.get("EMAIL")]
    rows = merge_rows(micro + web)
    render(rows)
    print(f"F1 CENTRALE TELEFONATE GUIDATE: {len(rows)} prospect")
    print(f"APRI: {OUT_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
