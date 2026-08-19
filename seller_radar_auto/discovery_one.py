#!/usr/bin/env python3
"""Discovery isolata: un comune per job GitHub Actions."""
import csv, html, json, os, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from search_engine import search

ROOT=Path(__file__).resolve().parent
PORTALS=ROOT/"portal_catalog.csv"
OUT=Path(os.getenv("F1_DISCOVERY_OUT", str(ROOT/"data"/"discovery_one.json")))
COMUNE=os.getenv("F1_COMUNE","").strip()
TRACK={"gclid","fbclid","msclkid","ref","source"}
PROPERTY_WORDS=("casa","appartamento","villa","villetta","trilocale","bilocale","quadrilocale","immobile","terratetto","monolocale","rustico","attico","alloggio","vendita","vendesi","house","property")
SALE_WORDS=("vendita","vendesi","vende","in vendita","€","euro","eur","for sale")
STREET_RE=re.compile(r"\b(via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo)\b",re.I)
BROAD_PATHS={"","^/.*$"}

def now(): return datetime.now(timezone.utc).isoformat()
def clean(s): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",s or ""))).strip()
def fold(s): return clean(s).casefold()
def norm(url):
    p=urlparse(url or ""); q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not(k.lower().startswith("utm_") or k.lower() in TRACK)]
    return urlunparse((p.scheme,p.netloc,p.path,p.params,urlencode(q),""))
def host_matches(host,expected):
    host=(host or "").lower().split(":")[0]; expected=(expected or "").lower().strip()
    if not expected: return True
    if expected.startswith("*."): return host.endswith(expected[1:])
    base=expected.removeprefix("www.")
    return host==expected or host==base or host.endswith("."+base)
def load_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))
def portal_for_url(url,portals):
    h=urlparse(url).netloc
    for p in portals:
        d=(p.get("domain") or "").strip()
        if d and host_matches(h,d): return p
    return None
def relevant(url,text,comune,portal=None):
    t=fold(text); c=fold(comune); p=urlparse(url); street=bool(STREET_RE.search(text or ""))
    if portal:
        path_regex=(portal.get("path_regex") or "").strip()
        if path_regex and not re.search(path_regex,p.path,re.I): return False
        if path_regex in BROAD_PATHS and not street: return False
    elif not street:
        return False
    if c and c not in t and c.replace(" ","-") not in url.casefold(): return False
    if not any(w in t for w in PROPERTY_WORDS): return False
    if not any(w in t for w in SALE_WORDS): return False
    return True
def price(text):
    pats=[
        r"(?:€|eur(?:o)?)\s*([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})",
        r"([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})\s*(?:€|eur(?:o)?)",
    ]
    for pat in pats:
        m=re.search(pat,text,re.I)
        if m:
            n=int(re.sub(r"\D","",m.group(1)))
            if 5000<=n<=20000000: return n
    return None
def seller_hint(text):
    t=fold(text)
    if re.search(r"\b(no agenzie|senza agenzia|da privato|annuncio privato|inserzionista privato|vendita privata|privato vende|vendo privatamente|solo privati)\b",t,re.I): return "INDIZIO_PRIVATO"
    if re.search(r"\b(agenzia immobiliare|tecnocasa|tecnorete|tempocasa|gabetti|re/?max|franchising immobiliare)\b",t,re.I): return "INDIZIO_AGENZIA"
    return "NON_DETERMINATO"

if not COMUNE:
    raise SystemExit("F1_COMUNE mancante")
portals=[r for r in load_csv(PORTALS) if r.get("enabled")=="1"]
plans=[
    ("Web generale",f'"{COMUNE}" (vendita OR "in vendita") (casa OR appartamento OR villa)',30,False),
    ("Web privati",f'"{COMUNE}" ("privato vende" OR "no agenzie" OR "da privato" OR "da privati") (casa OR appartamento OR villa)',20,True),
]
accepted=[]; statuses=[]; seen=set()
for label,query,count,private_query in plans:
    results,error=search(query,count); n=0
    for r in results:
        url=norm(r.get("url","")); title=clean(r.get("title","")); snippet=clean(r.get("snippet","")); evidence=f"{title} {snippet}".strip(); portal=portal_for_url(url,portals)
        if not relevant(url,evidence,COMUNE,portal): continue
        if url in seen: continue
        seen.add(url); n+=1
        accepted.append({
            "comune":COMUNE,"fonte":(portal.get("label") or "").strip() if portal else label,
            "url":url,"title":title[:220],"snippet":snippet[:500],"private_intent":bool(private_query or (portal and portal.get("private_intent")=="1")),
            "domain_rule":(portal.get("domain") or "") if portal else "","path_rule":(portal.get("path_regex") or "") if portal else "",
            "seller_hint":seller_hint(evidence),"price":price(evidence),"discovery_engine":"DDG_MATRIX_V1"
        })
    statuses.append({"FONTE":label,"COMUNE":COMUNE,"STATO":"OK" if not error else "ERROR","ULTIMO_CONTROLLO":now(),"RISULTATI_GREZZI":len(results),"ACCETTATI":n,"MESSAGGIO":error,"QUERY":query})
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps({"comune":COMUNE,"results":accepted,"status":statuses},ensure_ascii=False,indent=2),encoding="utf-8")
print(f"DISCOVERY {COMUNE}: {len(accepted)} accettati; " + ", ".join(f"{s['FONTE']}={s['STATO']}:{s['RISULTATI_GREZZI']}" for s in statuses))
