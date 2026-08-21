#!/usr/bin/env python3
"""Discovery isolata: un comune per job GitHub Actions.

Esegue sia le query generiche sia le query delle fonti abilitate in
portal_catalog.csv. Un annuncio valido non viene scartato soltanto perché
l'indirizzo/civico non è già presente nel risultato di ricerca: il livello
operativo successivo lo marca come DA VERIFICARE.
"""
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
    t=fold(text); c=fold(comune); p=urlparse(url)
    if portal:
        domain=(portal.get("domain") or "").strip()
        if domain and not host_matches(p.netloc,domain): return False
        path_regex=(portal.get("path_regex") or "").strip()
        if path_regex and path_regex not in BROAD_PATHS and not re.search(path_regex,p.path,re.I):
            return False
    if c and c not in t and c.replace(" ","-") not in url.casefold(): return False
    if not any(w in t for w in PROPERTY_WORDS): return False
    if not any(w in t for w in SALE_WORDS): return False
    # La via completa aumenta la qualità ma non è un requisito di ingresso.
    # prepare_acquisition_route.py gestisce INDIRIZZO/CIVICO DA VERIFICARE.
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

# Prima due query ad ampia copertura, poi tutte le fonti configurate.
plans=[
    {"label":"Mercato generale","query":f'"{COMUNE}" (vendita OR "in vendita") (casa OR appartamento OR villa)',"count":30,"private":False,"portal":None},
    {"label":"Privati generico","query":f'"{COMUNE}" ("privato vende" OR "no agenzie" OR "da privato" OR "da privati") (casa OR appartamento OR villa)',"count":20,"private":True,"portal":None},
]
for p in portals:
    template=(p.get("query_template") or "").strip()
    if not template: continue
    try: count=max(1,min(30,int(p.get("max_results") or 10)))
    except Exception: count=10
    plans.append({
        "label":(p.get("label") or "Fonte configurata").strip(),
        "query":template.replace("{comune}",COMUNE),
        "count":count,
        "private":p.get("private_intent")=="1",
        "portal":p,
    })

accepted=[]; statuses=[]; seen=set()
for plan in plans:
    results,error=search(plan["query"],plan["count"]); n=0
    for r in results:
        url=norm(r.get("url","")); title=clean(r.get("title","")); snippet=clean(r.get("snippet","")); evidence=f"{title} {snippet}".strip()
        detected=portal_for_url(url,portals)
        expected=plan.get("portal")
        # Nelle query site-specific la fonte attesa è vincolante; nelle query generiche
        # usiamo la fonte rilevata dall'URL, quando nota.
        portal=expected or detected
        if not relevant(url,evidence,COMUNE,portal): continue
        if url in seen: continue
        seen.add(url); n+=1
        source=(detected or expected or {}).get("label") or plan["label"]
        private_intent=bool(plan["private"] or ((detected or expected) and (detected or expected).get("private_intent")=="1"))
        accepted.append({
            "comune":COMUNE,"fonte":source.strip(),
            "url":url,"title":title[:220],"snippet":snippet[:700],"private_intent":private_intent,
            "domain_rule":((detected or expected) or {}).get("domain","") or "",
            "path_rule":((detected or expected) or {}).get("path_regex","") or "",
            "seller_hint":seller_hint(evidence),"price":price(evidence),
            "has_street_hint":bool(STREET_RE.search(evidence)),
            "discovery_engine":"PUBLIC_SEARCH_MATRIX_V2"
        })
    statuses.append({
        "FONTE":plan["label"],"COMUNE":COMUNE,"STATO":"OK" if not error else "ERROR",
        "ULTIMO_CONTROLLO":now(),"RISULTATI_GREZZI":len(results),"ACCETTATI":n,
        "MESSAGGIO":error,"QUERY":plan["query"]
    })

OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps({"comune":COMUNE,"results":accepted,"status":statuses},ensure_ascii=False,indent=2),encoding="utf-8")
print(f"DISCOVERY {COMUNE}: {len(accepted)} accettati su {len(plans)} query; " + ", ".join(f"{s['FONTE']}={s['STATO']}:{s['ACCETTATI']}/{s['RISULTATI_GREZZI']}" for s in statuses))
