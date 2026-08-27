#!/usr/bin/env python3
"""Discovery isolata: un Comune per job GitHub Actions.

Usa una matrice di query in stile Google Dork: frasi esatte, OR, site: e segnali
commerciali. Il motore cloud può usare più provider pubblici; la logica di ricerca
resta la stessa. Cerca mercato attivo, privati, agenzie, aste, ribassi e tracce
storiche/uscite. L'indirizzo non è requisito d'ingresso: viene arricchito dopo.
"""
import csv, html, json, os, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from search_engine import search

ROOT=Path(__file__).resolve().parent
PORTALS=ROOT/"portal_catalog.csv"
OUT=Path(os.getenv("F1_DISCOVERY_OUT",str(ROOT/"data"/"discovery_one.json")))
COMUNE=os.getenv("F1_COMUNE","").strip()
TRACK={"gclid","fbclid","msclkid","ref","source"}
PROPERTY_WORDS=("casa","appartamento","villa","villetta","trilocale","bilocale","quadrilocale","immobile","terratetto","monolocale","rustico","casale","cascina","mansarda","attico","alloggio","terreno","baita","vendita","vendesi")
SALE_WORDS=("vendita","vendesi","vende","in vendita","for sale","asta","giudiziaria","aggiudicato","venduto","prezzo ribassato","ribasso","prezzo ridotto","non disponibile","€","euro","eur")
STREET_RE=re.compile(r"\b(via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo|localit[aà])\b",re.I)
BROAD_PATHS={"","^/.*$"}

def now():return datetime.now(timezone.utc).isoformat()
def clean(s):return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",s or ""))).strip()
def fold(s):return clean(s).casefold()
def norm(url):
    p=urlparse(url or "");q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not(k.lower().startswith("utm_") or k.lower() in TRACK)]
    return urlunparse((p.scheme,p.netloc,p.path,p.params,urlencode(q),""))
def host_matches(host,expected):
    host=(host or "").lower().split(":")[0];expected=(expected or "").lower().strip()
    if not expected:return True
    if expected.startswith("*."):return host.endswith(expected[1:])
    base=expected.removeprefix("www.")
    return host==expected or host==base or host.endswith("."+base)
def load_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def portal_for_url(url,portals):
    h=urlparse(url).netloc
    for p in portals:
        d=(p.get("domain") or "").strip()
        if d and host_matches(h,d):return p
    return None
def relevant(url,text,comune,portal=None):
    t=fold(text);c=fold(comune);p=urlparse(url)
    if portal:
        domain=(portal.get("domain") or "").strip()
        if domain and not host_matches(p.netloc,domain):return False
        path_regex=(portal.get("path_regex") or "").strip()
        if path_regex and path_regex not in BROAD_PATHS and not re.search(path_regex,p.path,re.I):return False
    if c and c not in t and c.replace(" ","-") not in url.casefold():return False
    if not any(w in t for w in PROPERTY_WORDS):return False
    if not any(w in t for w in SALE_WORDS):return False
    return True
def price(text):
    for pat in [r"(?:€|eur(?:o)?)\s*([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})",r"([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})\s*(?:€|eur(?:o)?)"]:
        m=re.search(pat,text,re.I)
        if m:
            n=int(re.sub(r"\D","",m.group(1)))
            if 5000<=n<=20000000:return n
    return None
def seller_hint(text):
    t=fold(text)
    if re.search(r"\b(no agenzie|senza agenzia|da privato|annuncio privato|inserzionista privato|vendita privata|privato vende|vendo privatamente|solo privati|astenersi agenzie)\b",t,re.I):return "INDIZIO_PRIVATO"
    if re.search(r"\b(agenzia immobiliare|tecnocasa|tecnorete|tempocasa|gabetti|re/?max|franchising immobiliare|mediazione immobiliare)\b",t,re.I):return "INDIZIO_AGENZIA"
    return "NON_DETERMINATO"
def market_signal(text,label=""):
    t=fold(text+" "+label);out=[]
    rules=[("ASTA",r"\b(asta|giudiziaria|tribunale|aggiudicat)\b"),("RIBASSO",r"\b(ribass|prezzo ridotto|prezzo trattabile|riduzione prezzo)\b"),("STORICO_USCITA",r"\b(venduto|non disponibile|non più disponibile|annuncio rimosso|scaduto)\b"),("PRIVATO",r"\b(privato|no agenzie|astenersi agenzie)\b"),("AGENZIA",r"\b(agenzia immobiliare|tecnocasa|tecnorete|tempocasa|gabetti|re/?max)\b")]
    for lab,pat in rules:
        if re.search(pat,t,re.I):out.append(lab)
    return ",".join(out) or "VENDITA"

if not COMUNE:raise SystemExit("F1_COMUNE mancante")
portals=[r for r in load_csv(PORTALS) if r.get("enabled")=="1"]

# Query ad ampia copertura costruite con logica Dork.
plans=[
 {"label":"Mercato generale","query":f'"{COMUNE}" ("in vendita" OR vendesi OR vendita) (casa OR appartamento OR villa OR immobile)',"count":30,"private":False,"portal":None},
 {"label":"Tipologie complete","query":f'"{COMUNE}" (appartamento OR villa OR rustico OR casale OR cascina OR "casa indipendente" OR terreno OR mansarda OR attico) ("in vendita" OR vendita OR vendesi)',"count":30,"private":False,"portal":None},
 {"label":"Ribassi","query":f'"{COMUNE}" (ribassato OR ribasso OR "prezzo ridotto" OR "prezzo trattabile") (casa OR appartamento OR villa OR rustico OR immobile)',"count":25,"private":False,"portal":None},
 {"label":"Aste","query":f'"{COMUNE}" ("asta giudiziaria" OR "vendita giudiziaria" OR "asta immobiliare" OR tribunale) (casa OR appartamento OR villa OR immobile)',"count":25,"private":False,"portal":None},
 {"label":"Agenzie","query":f'"{COMUNE}" ("agenzia immobiliare" OR immobiliare) ("in vendita" OR vendita OR vendesi) (casa OR appartamento OR villa OR rustico)',"count":25,"private":False,"portal":None},
 {"label":"Privati generico","query":f'"{COMUNE}" ("privato vende" OR "no agenzie" OR "astenersi agenzie" OR "da privato" OR "da privati") (casa OR appartamento OR villa OR rustico)',"count":25,"private":True,"portal":None},
 {"label":"Storico uscite","query":f'"{COMUNE}" (venduto OR "annuncio non disponibile" OR "immobile non disponibile" OR "non più disponibile" OR "annuncio rimosso") (casa OR appartamento OR villa OR immobile)',"count":20,"private":False,"portal":None},
]
for p in portals:
    template=(p.get("query_template") or "").strip()
    if not template:continue
    try:count=max(1,min(30,int(p.get("max_results") or 10)))
    except Exception:count=10
    plans.append({"label":(p.get("label") or "Fonte configurata").strip(),"query":template.replace("{comune}",COMUNE),"count":count,"private":p.get("private_intent")=="1","portal":p})

accepted=[];statuses=[];seen=set()
for plan in plans:
    results,error=search(plan["query"],plan["count"]);nacc=0
    for r in results:
        url=norm(r.get("url",""));title=clean(r.get("title",""));snippet=clean(r.get("snippet",""));evidence=f"{title} {snippet}".strip();detected=portal_for_url(url,portals);expected=plan.get("portal");portal=expected or detected
        if not relevant(url,evidence,COMUNE,portal) or url in seen:continue
        seen.add(url);nacc+=1;source=(detected or expected or {}).get("label") or plan["label"];private_intent=bool(plan["private"] or ((detected or expected) and (detected or expected).get("private_intent")=="1"))
        accepted.append({"comune":COMUNE,"fonte":source.strip(),"url":url,"title":title[:220],"snippet":snippet[:700],"private_intent":private_intent,"domain_rule":((detected or expected) or {}).get("domain","") or "","path_rule":((detected or expected) or {}).get("path_regex","") or "","seller_hint":seller_hint(evidence),"price":price(evidence),"has_street_hint":bool(STREET_RE.search(evidence)),"market_signal":market_signal(evidence,plan["label"]),"query_label":plan["label"],"discovery_engine":"PUBLIC_DORK_MATRIX_V3"})
    statuses.append({"FONTE":plan["label"],"COMUNE":COMUNE,"STATO":"OK" if not error else "ERROR","ULTIMO_CONTROLLO":now(),"RISULTATI_GREZZI":len(results),"ACCETTATI":nacc,"MESSAGGIO":error,"QUERY":plan["query"]})

OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps({"comune":COMUNE,"results":accepted,"status":statuses},ensure_ascii=False,indent=2),encoding="utf-8")
print(f"DISCOVERY {COMUNE}: {len(accepted)} accettati su {len(plans)} query; "+", ".join(f"{s['FONTE']}={s['STATO']}:{s['ACCETTATI']}/{s['RISULTATI_GREZZI']}" for s in statuses))
