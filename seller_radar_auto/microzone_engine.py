#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 — Microzona: via annuncio + 4 vie realmente vicine.

Input:
- data/area_radar.csv (preferito)
- data/intelligence/immobili_snapshot.csv (fallback)

Output pubblico (NESSUN telefono/nome):
- data/microzone_targets.csv
- data/microzone_targets.json

La geometria stradale viene letta da OpenStreetMap tramite Overpass, una volta
per comune e con cache locale. Non vengono usati dati personali.
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
        via = street_only(r.get("VIA_RADAR") or r.get("TARGET") or "")
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
        via = street_only(r.get("strada") or r.get("via") or "")
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
                        "User-Agent": cfg.get("user_agent", "F1Immobiliare-Microzone/1.1"),
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


def main():
    cfg = load_config()
    targets = target_streets(cfg)
    by_city = {}
    for x in targets:
        by_city.setdefault(x["comune"], []).append(x)

    rows = []
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "main_towns": cfg["main_towns"], "microzones": []}
    for city_index, (comune, items) in enumerate(sorted(by_city.items())):
        if city_index:
            time.sleep(2.5)
        try:
            roads = overpass_roads(comune, cfg)
            osm_status = "OK"
        except Exception as e:
            print(f"[WARN] OSM {comune}: {e}")
            roads = []
            osm_status = "FALLBACK_SOLO_TARGET"

        for x in items:
            near = nearest_streets(x["target_street"], roads, int(cfg.get("nearby_streets_per_target", 4))) if roads else []
            zone_id = slug(comune + "-" + x["target_street"])
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
            summary["microzones"].append({
                "zone_id": zone_id,
                "comune": comune,
                "target_street": x["target_street"],
                "listing_target": x.get("listing_target", ""),
                "listing_url": x.get("listing_url", ""),
                "streets": [x["target_street"]] + [n["street"] for n in near],
                "osm_status": osm_status,
            })

    DATA.mkdir(parents=True, exist_ok=True)
    fields = ["ZONE_ID","COMUNE","VIA_ANNUNCIO","RIFERIMENTO_ANNUNCIO","ANNUNCIO_URL","RANK","TIPO_VIA","VIA_DA_LAVORARE","DISTANZA_M","RELAZIONE","OSM_STATUS"]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Microzone F1: {len(summary['microzones'])} zone, {len(rows)} righe strada. Nessun dato personale pubblicato.")


if __name__ == "__main__":
    main()
