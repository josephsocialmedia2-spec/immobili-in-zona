#!/usr/bin/env python3
from __future__ import annotations
import csv, json, math, time, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
SRC=ROOT/"municipalities.csv"
OUT=DATA/"municipalities_operational.csv"
CACHE=DATA/"municipality_geocodes.json"
CFG=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
CENTER=CFG["center"]["name"]
RADIUS=float(CFG["center"]["radius_km"])
UA="F1SellerRadar/1.0 (territory geocoder; public municipality data)"

def hav(lat1,lon1,lat2,lon2):
    R=6371.0088
    p1,p2=math.radians(lat1),math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def geocode(name, cache):
    if name in cache:
        return cache[name]
    q=urllib.parse.urlencode({"q":f"{name}, Torino, Piemonte, Italia","format":"jsonv2","limit":1,"countrycodes":"it"})
    req=urllib.request.Request("https://nominatim.openstreetmap.org/search?"+q,headers={"User-Agent":UA,"Accept-Language":"it"})
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            rows=json.loads(r.read().decode("utf-8","replace"))
        if rows:
            val={"lat":float(rows[0]["lat"]),"lon":float(rows[0]["lon"]),"display_name":rows[0].get("display_name","")}
            cache[name]=val
            time.sleep(1.05)
            return val
    except Exception as e:
        cache[name]={"error":str(e)}
        time.sleep(1.05)
    return None

DATA.mkdir(exist_ok=True)
cache={}
if CACHE.exists():
    try: cache=json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception: cache={}

center=geocode(CENTER,cache)
if not center or "lat" not in center:
    raise SystemExit(f"Impossibile geocodificare il centro: {CENTER}")

with SRC.open(encoding="utf-8-sig",newline="") as f:
    candidates=list(csv.DictReader(f))

rows=[]
for r in candidates:
    comune=(r.get("comune") or "").strip()
    if not comune: continue
    g=geocode(comune,cache)
    if g and "lat" in g:
        d=hav(center["lat"],center["lon"],g["lat"],g["lon"])
        enabled=1 if d <= RADIUS else 0
        rows.append({"enabled":enabled,"comune":comune,"distance_km":f"{d:.2f}","lat":g["lat"],"lon":g["lon"],"geocode_status":"OK"})
    else:
        # fallback conservativo: usa il flag precedente ma segnala il mancato calcolo
        enabled=1 if str(r.get("enabled","")).strip()=="1" else 0
        rows.append({"enabled":enabled,"comune":comune,"distance_km":"","lat":"","lon":"","geocode_status":"FALLBACK_ORIGINALE"})

CACHE.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding="utf-8")
with OUT.open("w",encoding="utf-8-sig",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["enabled","comune","distance_km","lat","lon","geocode_status"])
    w.writeheader(); w.writerows(rows)

inside=[r for r in rows if str(r["enabled"])=="1"]
print(json.dumps({"center":CENTER,"radius_km":RADIUS,"candidates":len(rows),"inside_radius":len(inside),"output":str(OUT)},ensure_ascii=False))
