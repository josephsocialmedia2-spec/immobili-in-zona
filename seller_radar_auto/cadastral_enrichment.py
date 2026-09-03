#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 Seller Radar — arricchimento catastale per indirizzo, senza dati personali.

Preserva i 660 record storici e aggiunge il contesto RADAR LIVE solo per la verifica
tecnica dell'immobile. Per gli immobili target (alloggi, ville, case indipendenti,
rustici, attività/locali commerciali) tenta:
  indirizzo -> geocoding pubblico -> GetFeatureInfo WMS Catasto AdE -> mappale.

Non ricerca intestatari, persone fisiche, telefoni o email.
"""
from __future__ import annotations

import csv, hashlib, html as htmllib, json, os, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MASTER = DATA / "seller_master_660_classificato.csv"
LIVE = DATA / "work_queue.csv"
OUT = DATA / "cadastral_enrichment.csv"
SUMMARY = DATA / "cadastral_summary.json"
CACHE = DATA / "cadastral_geocode_cache.json"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
WMS = "https://wms.cartografia.agenziaentrate.gov.it/inspire/wms/ows01.php"
UA = "F1Immobiliare-Catasto/1.0 (address-to-parcel public-data verification; f1immobiliaresusa@outlook.it)"
TARGET_TYPES = {
    "APPARTAMENTO", "VILLA", "CASA_INDIPENDENTE_TERRATETTO",
    "RUSTICO_CASALE_BAITA", "NEGOZIO_COMMERCIALE",
}
COMMERCIAL_RE = re.compile(r"\b(attivit[aà]|locale\s+commerciale|negozio|bottega)\b", re.I)
INVALID_ADDRESS_RE = re.compile(r"(da verificare|non disponibile|indirizzo remoto|^-$|^—$)", re.I)
LOCALID_RE = re.compile(r"IT\.AGE\.PLA\.[A-Z0-9]+_[A-Z0-9]+(?:\.[A-Z0-9]+)+", re.I)
CIVIC_RE = re.compile(r"\b\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|\s*[A-Za-z])?\s*$")
FIELDS = [
    "RECORD_KEY","MASTER_660_ID","ORIGINE","NOVITA","COMUNE","TITOLO","TIPOLOGIA",
    "INDIRIZZO","TARGET_RICERCA","STATO_RICERCA","LAT","LON","GEOCODE_DISPLAY",
    "CATASTO_LOCAL_ID","CODICE_BELFIORE","FOGLIO_RAW","PARTICELLA","FONTE_CATASTO",
    "URL_SEGNALE","PRIMA_RILEVAZIONE","ULTIMO_CONTROLLO_CATASTO",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv(path: Path) -> list[dict]:
    if not path.exists(): return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_json(path: Path, default):
    try: return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception: return default


def norm_url(value: str) -> str:
    s = str(value or "").strip()
    if not s: return ""
    try:
        p = urllib.parse.urlsplit(s)
        path = re.sub(r"/+$", "", p.path or "/")
        return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, p.query, ""))
    except Exception:
        return s


def targeted(row: dict) -> bool:
    typ = (row.get("TIPOLOGIA_REALE_INFERITA") or row.get("TIPOLOGIA") or "").strip().upper()
    title = str(row.get("TITOLO") or "")
    return typ in TARGET_TYPES or bool(COMMERCIAL_RE.search(title))


def address_for(row: dict) -> str:
    for k in ("DOVE_ANDRE", "VIA_RADAR", "INDIRIZZO"):
        v = str(row.get(k) or "").strip(" ,.;")
        if v and not INVALID_ADDRESS_RE.search(v):
            return v
    return ""


def has_civic(address: str) -> bool:
    return bool(address and CIVIC_RE.search(address))


def request_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language":"it-IT,it;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(1_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")


def geocode(address: str, comune: str, cache: dict) -> tuple[str,str,str,str]:
    q = f"{address}, {comune}, Torino, Piemonte, Italia"
    key = q.casefold()
    if key in cache:
        x = cache[key] or {}
        return str(x.get("lat", "")), str(x.get("lon", "")), str(x.get("display_name", "")), "CACHE"
    params = urllib.parse.urlencode({"q": q, "format":"jsonv2", "limit":1, "countrycodes":"it", "addressdetails":1})
    try:
        body = request_text(NOMINATIM + "?" + params, 25)
        arr = json.loads(body)
        if arr:
            x = {"lat": arr[0].get("lat"), "lon": arr[0].get("lon"), "display_name": arr[0].get("display_name", "")}
            cache[key] = x
            return str(x["lat"] or ""), str(x["lon"] or ""), str(x["display_name"] or ""), "WEB"
        cache[key] = None
        return "", "", "", "NON_TROVATO"
    except Exception as e:
        return "", "", "", "ERRORE_GEOCODE:" + type(e).__name__


def parcel_info(lat: str, lon: str) -> tuple[str,str]:
    try:
        y, x = float(lat), float(lon)
    except Exception:
        return "", "COORDINATE_NON_VALIDE"
    # WMS 1.1.1 evita l'ambiguità axis-order della 1.3.0; EPSG:4258 usa coordinate geografiche ETRS89.
    dx = dy = 0.000025
    params = {
        "REQUEST":"GetFeatureInfo", "SERVICE":"WMS", "SRS":"EPSG:4258", "STYLES":"",
        "VERSION":"1.1.1", "FORMAT":"image/png", "BBOX":f"{x-dx},{y-dy},{x+dx},{y+dy}",
        "HEIGHT":"9", "WIDTH":"9", "LAYERS":"CP.CadastralParcel",
        "QUERY_LAYERS":"CP.CadastralParcel", "INFO_FORMAT":"text/html", "X":"5", "Y":"5",
    }
    try:
        body = request_text(WMS + "?" + urllib.parse.urlencode(params), 35)
    except Exception as e:
        return "", "ERRORE_WMS:" + type(e).__name__
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", body))
    m = LOCALID_RE.search(text)
    if not m:
        m = LOCALID_RE.search(body)
    return (m.group(0).upper(), "OK") if m else ("", "NESSUN_MAPPALE_AL_PUNTO")


def parse_localid(local_id: str) -> tuple[str,str,str]:
    m = re.match(r"IT\.AGE\.PLA\.([A-Z0-9]+)_([A-Z0-9]+)\.([A-Z0-9]+)", local_id or "", re.I)
    return (m.group(1).upper(), m.group(2).upper(), m.group(3).upper()) if m else ("", "", "")


def live_is_new(row: dict) -> bool:
    if str(row.get("STATO") or "").upper() == "NEW": return True
    v = str(row.get("PRIMA_RILEVAZIONE") or "").strip()
    if not v: return False
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() <= 86400
    except Exception:
        return False


def main() -> int:
    master = read_csv(MASTER)
    live = read_csv(LIVE)
    if len(master) != 660:
        raise SystemExit(f"FAIL: master storico atteso 660, trovato {len(master)}")

    live_by_url = {norm_url(r.get("URL")): r for r in live if norm_url(r.get("URL"))}
    master_urls = {norm_url(r.get("URL")) for r in master if norm_url(r.get("URL"))}
    previous = {r.get("RECORD_KEY",""): r for r in read_csv(OUT) if r.get("RECORD_KEY")}
    cache = load_json(CACHE, {})

    records: list[dict] = []
    for r in master:
        u = norm_url(r.get("URL")); lr = live_by_url.get(u, {})
        merged = dict(r)
        for k in ("DOVE_ANDRE","VIA_RADAR","STATO","PRIMA_RILEVAZIONE"):
            if lr.get(k): merged[k] = lr[k]
        records.append({"key": "M660-" + str(r.get("MASTER_660_ID") or ""), "origin":"MASTER_660", "master":r.get("MASTER_660_ID") or "", "row":merged, "live":lr})

    for r in live:
        u = norm_url(r.get("URL"))
        if not u or u in master_urls: continue
        k = "LIVE-" + hashlib.sha256(u.encode("utf-8")).hexdigest()[:16]
        records.append({"key":k, "origin":"RADAR_LIVE", "master":"", "row":r, "live":r})

    out = []
    geocode_web_calls = 0
    wms_calls = 0
    for idx, rec in enumerate(records, 1):
        r, lr = rec["row"], rec["live"]
        typ = (r.get("TIPOLOGIA_REALE_INFERITA") or r.get("TIPOLOGIA") or "NON_CLASSIFICATO").strip().upper()
        addr = address_for(r)
        target = targeted(r)
        novelty = "SI" if (lr and live_is_new(lr)) else "NO"
        old = previous.get(rec["key"], {})
        row = {k:"" for k in FIELDS}
        row.update({
            "RECORD_KEY":rec["key"], "MASTER_660_ID":rec["master"], "ORIGINE":rec["origin"],
            "NOVITA":novelty, "COMUNE":r.get("COMUNE") or "", "TITOLO":r.get("TITOLO") or "",
            "TIPOLOGIA":typ, "INDIRIZZO":addr, "TARGET_RICERCA":"SI" if target else "NO",
            "URL_SEGNALE":r.get("URL") or "", "PRIMA_RILEVAZIONE":lr.get("PRIMA_RILEVAZIONE") or r.get("PRIMA_RILEVAZIONE") or "",
            "FONTE_CATASTO":"Agenzia delle Entrate · WMS CP.CadastralParcel",
        })
        same_address = old.get("INDIRIZZO") == addr and old.get("COMUNE") == row["COMUNE"]
        reusable = same_address and old.get("STATO_RICERCA") in {"MAPPALE_VERIFICATO","NON_TARGET","INDIRIZZO_SENZA_CIVICO","GEOCODE_NON_TROVATO"}
        if reusable:
            for k in ("STATO_RICERCA","LAT","LON","GEOCODE_DISPLAY","CATASTO_LOCAL_ID","CODICE_BELFIORE","FOGLIO_RAW","PARTICELLA","ULTIMO_CONTROLLO_CATASTO"):
                row[k] = old.get(k, "")
            out.append(row); continue

        row["ULTIMO_CONTROLLO_CATASTO"] = now()
        if not target:
            row["STATO_RICERCA"] = "NON_TARGET"
            out.append(row); continue
        if not addr or not has_civic(addr):
            row["STATO_RICERCA"] = "INDIRIZZO_SENZA_CIVICO"
            out.append(row); continue

        lat, lon, display, gstatus = geocode(addr, row["COMUNE"], cache)
        if gstatus == "WEB":
            geocode_web_calls += 1
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            time.sleep(float(os.getenv("F1_NOMINATIM_INTERVAL", "1.1")))
        row["LAT"], row["LON"], row["GEOCODE_DISPLAY"] = lat, lon, display
        if not lat or not lon:
            row["STATO_RICERCA"] = "GEOCODE_NON_TROVATO" if gstatus == "NON_TROVATO" else gstatus
            out.append(row); continue

        local_id, pstatus = parcel_info(lat, lon); wms_calls += 1
        row["CATASTO_LOCAL_ID"] = local_id
        if local_id:
            belf, foglio, part = parse_localid(local_id)
            row["CODICE_BELFIORE"], row["FOGLIO_RAW"], row["PARTICELLA"] = belf, foglio, part
            row["STATO_RICERCA"] = "MAPPALE_VERIFICATO"
        else:
            row["STATO_RICERCA"] = pstatus
        out.append(row)
        if idx % 25 == 0:
            print(f"CATASTO progress {idx}/{len(records)} | geocode_web={geocode_web_calls} wms={wms_calls}")

    DATA.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(out)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    base660 = [r for r in out if r["ORIGINE"] == "MASTER_660"]
    summary = {
        "generated_at": now(), "master_660_rows": len(base660), "total_records_with_live": len(out),
        "target_master_660": sum(r["TARGET_RICERCA"]=="SI" for r in base660),
        "mappali_verificati_master_660": sum(r["STATO_RICERCA"]=="MAPPALE_VERIFICATO" for r in base660),
        "indirizzi_senza_civico_master_660": sum(r["STATO_RICERCA"]=="INDIRIZZO_SENZA_CIVICO" for r in base660),
        "novita_live": sum(r["NOVITA"]=="SI" for r in out),
        "geocode_web_calls": geocode_web_calls, "wms_calls": wms_calls,
        "policy": "NO_PERSONAL_DATA_ONLY_ADDRESS_TO_CADASTRAL_PARCEL",
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if len(base660) != 660:
        raise SystemExit(f"FAIL output base660={len(base660)}")
    print("PASS CATASTO | " + json.dumps(summary, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
