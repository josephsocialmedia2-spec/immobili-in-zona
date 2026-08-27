#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 — Microzona: via annuncio + massimo 4 vie realmente vicine.

Input:
- data/area_radar.csv (preferito)
- data/intelligence/immobili_snapshot.csv (fallback)

Output pubblico (NESSUN telefono/nome):
- data/microzone_targets.csv
- data/microzone_targets.json

Le strade arrivano da OpenStreetMap/Overpass. Se il nome della via target non
combacia con la rete OSM, viene geocodificato solo quel target tramite Nominatim
con cache persistente e massimo 4 richieste/minuto; poi si selezionano le strade
nominate più vicine. Non vengono inviati dati personali.

I target che restano geograficamente non risolti vengono conservati nel JSON
come quarantena diagnostica, ma NON entrano nel CSV operativo usato dal motore
telefonico locale.
"""
from __future__ import annotations

import csv
import json
import math
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CONFIG_PATH = ROOT / "f1_microzone_config.json"
AREA = DATA / "area_radar.csv"
SNAP = DATA / "intelligence" / "immobili_snapshot.csv"
OUT_CSV = DATA / "microzone_targets.csv"
OUT_JSON = DATA / "microzone_targets.json"
CACHE = DATA / "osm_microzone_cache"
GEOCODE_CACHE = DATA / "osm_geocode_cache.json"
_LAST_GEOCODE_CALL = 0.0


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("’", "'")
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def street_only(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip(" ,.;")
    s = re.sub(r"\s+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|\s*[A-Za-z])?\s*$", "", s).strip()
    return s


def target_street(raw: str, comune: str) -> str:
    s = str(raw or "").strip()
    # Togli il comune SOLO quando è una coda esplicita separata da virgola.
    # Non trasformare mai "Via Almese" in "Via" quando il comune è Almese.
    if comune:
        s = re.sub(rf",\s*{re.escape(comune)}\s*$", "", s, flags=re.I).strip(" ,")
    return street_only(s)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-") or "comune"


def read_csv(path: Path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def target_streets(cfg):
    allowed = {norm(x): x for x in cfg["main_towns"]}
    excluded = {norm(x) for x in cfg.get("excluded_towns", [])}
    out = {}

    for r in read_csv(AREA):
        comune = (r.get("COMUNE") or "").strip()
        if norm(comune) not in allowed or norm(comune) in excluded:
            continue
        via = target_street(r.get("VIA_RADAR") or r.get("TARGET") or "", comune)
        if not via or "indirizzo da verificare" in norm(via):
            continue
        key = (norm(comune), norm(via))
        out[key] = {
            "comune": allowed[norm(comune)],
            "target_street": via,
            "listing_target": (r.get("TARGET") or "").strip(),
            "listing_url": (r.get("FONTE") or "").strip(),
            "score": (r.get("SCORE") or "").strip(),
            "source": "area_radar",
        }

    if out:
        return list(out.values())

    for r in read_csv(SNAP):
        comune = (r.get("comune") or "").strip()
        if norm(comune) not in allowed or norm(comune) in excluded:
            continue
        if str(r.get("attivo", "")).strip().lower() not in {"true", "1", "si", "yes"}:
            continue
        via = target_street(r.get("strada") or r.get("via") or "", comune)
        if not via:
            continue
        key = (norm(comune), norm(via))
        out[key] = {
            "comune": allowed[norm(comune)],
            "target_street": via,
            "listing_target": (r.get("via") or "").strip(),
            "listing_url": (r.get("url") or "").strip(),
            "score": "",
            "source": "snapshot",
        }
    return list(out.values())


def cache_fresh(path: Path, days: int) -> bool:
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < days * 86400


def overpass_roads(comune: str, cfg):
    CACHE.mkdir(parents=True, exist_ok=True)
    cp = CACHE / f"{slug(comune)}.json"
    if cache_fresh(cp, int(cfg.get("osm_cache_days", 7))):
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass

    q = f'''[out:json][timeout:35];
area["boundary"="administrative"]["name"="{comune}"]->.a;
way(area.a)["highway"]["name"];
out body geom;'''
    data = urllib.parse.urlencode({"data": q}).encode("utf-8")
    urls = cfg.get("overpass_urls") or [cfg.get("overpass_url", "https://overpass-api.de/api/interpreter")]
    last_error = None
    obj = None
    for endpoint in urls:
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=data,
                    headers={
                        "User-Agent": cfg.get("user_agent", "F1Immobiliare-Microzone/1.2"),
                        "Accept": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=45) as res:
                    obj = json.loads(res.read().decode("utf-8"))
                if obj is not None:
                    break
            except Exception as e:
                last_error = e
                wait = 4 + attempt * 4
                print(f"[WARN] Overpass {endpoint} {comune} tentativo {attempt+1}: {e}; retry in {wait}s")
                time.sleep(wait)
        if obj is not None:
            break
    if obj is None:
        raise RuntimeError(f"Tutte le istanze Overpass fallite per {comune}: {last_error}")

    roads = []
    for e in obj.get("elements", []):
        name = (e.get("tags") or {}).get("name")
        geom = e.get("geometry") or []
        nodes = e.get("nodes") or []
        if not name or len(geom) < 2:
            continue
        roads.append({
            "id": e.get("id"),
            "name": name,
            "nodes": nodes,
            "geometry": [[p.get("lat"), p.get("lon")] for p in geom if p.get("lat") is not None and p.get("lon") is not None],
        })
    cp.write_text(json.dumps(roads, ensure_ascii=False), encoding="utf-8")
    return roads


def load_geocode_cache():
    try:
        return json.loads(GEOCODE_CACHE.read_text(encoding="utf-8")) if GEOCODE_CACHE.exists() else {}
    except Exception:
        return {}


def save_geocode_cache(obj):
    GEOCODE_CACHE.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def geocode_target(street: str, comune: str, cfg):
    global _LAST_GEOCODE_CALL
    cache = load_geocode_cache()
    key = norm(f"{street}|{comune}")
    if key in cache:
        value = cache[key]
        if value and value.get("lat") is not None and value.get("lon") is not None:
            return [float(value["lat"]), float(value["lon"])]
        return None

    interval = max(15.0, float(cfg.get("nominatim_min_interval_seconds", 15)))
    elapsed = time.time() - _LAST_GEOCODE_CALL
    if elapsed < interval:
        time.sleep(interval - elapsed)

    params = urllib.parse.urlencode({
        "q": f"{street}, {comune}, Torino, Piemonte, Italia",
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "it",
        "addressdetails": 0,
    })
    url = cfg.get("nominatim_url", "https://nominatim.openstreetmap.org/search") + "?" + params
    req = urllib.request.Request(url, headers={
        "User-Agent": cfg.get("user_agent", "F1Immobiliare-Microzone/1.2"),
        "Accept": "application/json",
    })
    try:
        _LAST_GEOCODE_CALL = time.time()
        with urllib.request.urlopen(req, timeout=25) as res:
            items = json.loads(res.read().decode("utf-8"))
        if items:
            point = {"lat": float(items[0]["lat"]), "lon": float(items[0]["lon"]), "display_name": items[0].get("display_name", "")}
            cache[key] = point
            save_geocode_cache(cache)
            return [point["lat"], point["lon"]]
        cache[key] = None
        save_geocode_cache(cache)
    except Exception as e:
        print(f"[WARN] Nominatim {street}, {comune}: {e}")
    return None


def hav(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2-lat1, lon2-lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def min_geom_distance(ga, gb):
    if not ga or not gb:
        return 10**9
    def sample(g):
        if len(g) <= 18:
            return g
        step = max(1, len(g)//18)
        return g[::step][:18] + [g[-1]]
    aa, bb = sample(ga), sample(gb)
    return min(hav(a,b) for a in aa for b in bb)


def group_by_name(roads):
    g = {}
    for r in roads:
        k = norm(r["name"])
        d = g.setdefault(k, {"name": r["name"], "nodes": set(), "geometry": []})
        d["nodes"].update(r.get("nodes") or [])
        d["geometry"].extend(r.get("geometry") or [])
    return g


def nearest_streets(target: str, roads, limit: int):
    grouped = group_by_name(roads)
    tk = norm(target)
    t = grouped.get(tk)
    if not t:
        matches = [(k,v) for k,v in grouped.items() if tk in k or k in tk]
        if matches:
            matches.sort(key=lambda kv: abs(len(kv[0])-len(tk)))
            tk, t = matches[0]
    if not t:
        return []

    ranked = []
    for k, v in grouped.items():
        if k == tk:
            continue
        intersects = bool(t["nodes"] & v["nodes"])
        dist = 0.0 if intersects else min_geom_distance(t["geometry"], v["geometry"])
        ranked.append((0 if intersects else 1, dist, v["name"]))
    ranked.sort(key=lambda x: (x[0], x[1], norm(x[2])))

    out, seen = [], set()
    for interflag, dist, name in ranked:
        k = norm(name)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append({
            "street": name,
            "distance_m": int(round(dist)),
            "relation": "INCROCIA" if interflag == 0 else "VICINA",
        })
        if len(out) >= limit:
            break
    return out


def nearest_from_point(point, target: str, roads, limit: int):
    grouped = group_by_name(roads)
    ranked = []
    for k, v in grouped.items():
        if k == norm(target) or not v["geometry"]:
            continue
        sampled = v["geometry"][::max(1, len(v["geometry"])//24)]
        dist = min(hav(point, p) for p in sampled)
        ranked.append((dist, v["name"]))
    ranked.sort(key=lambda x: (x[0], norm(x[1])))
    out=[]; seen=set()
    for dist, name in ranked:
        k=norm(name)
        if k in seen:
            continue
        seen.add(k)
        out.append({"street":name,"distance_m":int(round(dist)),"relation":"VICINA_GEOCODE"})
        if len(out)>=limit:
            break
    return out


def main():
    cfg = load_config()
    targets = target_streets(cfg)
    by_city = {}
    for x in targets:
        by_city.setdefault(x["comune"], []).append(x)

    rows = []
    quarantine = []
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "main_towns": cfg["main_towns"],
        "map_data_attribution": cfg.get("map_data_attribution", "Data © OpenStreetMap contributors, ODbL 1.0"),
        "microzones": [],
        "quarantine": quarantine,
    }
    for city_index, (comune, items) in enumerate(sorted(by_city.items())):
        if city_index:
            time.sleep(2.5)
        try:
            roads = overpass_roads(comune, cfg)
            city_status = "OK"
        except Exception as e:
            print(f"[WARN] OSM {comune}: {e}")
            roads = []
            city_status = "FALLBACK_SOLO_TARGET"

        for x in items:
            limit = int(cfg.get("nearby_streets_per_target", 4))
            near = nearest_streets(x["target_street"], roads, limit) if roads else []
            osm_status = city_status
            if roads and len(near) < limit:
                point = geocode_target(x["target_street"], comune, cfg)
                if point:
                    near = nearest_from_point(point, x["target_street"], roads, limit)
                    osm_status = "OK_GEOCODE_FALLBACK"
                elif not near:
                    osm_status = "TARGET_NON_RISOLTA"

            zone_id = slug(comune + "-" + x["target_street"])
            micro = {
                "zone_id": zone_id,
                "comune": comune,
                "target_street": x["target_street"],
                "listing_target": x.get("listing_target", ""),
                "listing_url": x.get("listing_url", ""),
                "streets": [x["target_street"]] + [n["street"] for n in near],
                "osm_status": osm_status,
            }

            # Un target non risolto non deve generare ricerche telefoniche.
            if osm_status in {"TARGET_NON_RISOLTA", "FALLBACK_SOLO_TARGET"} or not near:
                quarantine.append({**micro, "reason": "POSIZIONE/VIA DA VERIFICARE"})
                print(f"[QUARANTENA] {comune} — {x['target_street']}: {osm_status}")
                continue

            base = {
                "ZONE_ID": zone_id,
                "COMUNE": comune,
                "VIA_ANNUNCIO": x["target_street"],
                "RIFERIMENTO_ANNUNCIO": x.get("listing_target", ""),
                "ANNUNCIO_URL": x.get("listing_url", ""),
                "OSM_STATUS": osm_status,
            }
            rows.append({**base, "RANK": 0, "TIPO_VIA": "TARGET", "VIA_DA_LAVORARE": x["target_street"], "DISTANZA_M": 0, "RELAZIONE": "CENTRO"})
            for i, n in enumerate(near, 1):
                rows.append({**base, "RANK": i, "TIPO_VIA": "VICINA", "VIA_DA_LAVORARE": n["street"], "DISTANZA_M": n["distance_m"], "RELAZIONE": n["relation"]})
            summary["microzones"].append(micro)

    DATA.mkdir(parents=True, exist_ok=True)
    fields = ["ZONE_ID","COMUNE","VIA_ANNUNCIO","RIFERIMENTO_ANNUNCIO","ANNUNCIO_URL","RANK","TIPO_VIA","VIA_DA_LAVORARE","DISTANZA_M","RELAZIONE","OSM_STATUS"]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Microzone F1 operative: {len(summary['microzones'])}; quarantena: {len(quarantine)}; righe strada: {len(rows)}. Nessun dato personale pubblicato.")


if __name__ == "__main__":
    main()
