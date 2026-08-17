#!/usr/bin/env python3
"""Worker isolato per un annuncio: cross-match, indirizzo e radar della stessa via."""
import html, json, os, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen
from search_engine import search

ROOT=Path(__file__).resolve().parent
STATE=ROOT/"data"/"state.json"
ITEM_ID=os.getenv("F1_ITEM_ID","").strip()
OUT=Path(os.getenv("F1_ITEM_OUT",str(ROOT/"data"/"item_result.json")))
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
TIMEOUT=18
TRACK={"gclid","fbclid","msclkid","ref","source"}
PHONE_RE=re.compile(r"(?<!\d)(?:\+39[\s.\-]?)?(?:0\d{1,3}[\s.\-]?\d{5,8}|3\d{2}[\s.\-]?\d{6,7})(?!\d)")
EMAIL_RE=re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",re.I)
ADDRESS_RE=re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s,]{2,80}?[,\s]+\d{1,4}(?:/[A-Za-z0-9]+|[A-Za-z])?\b",re.I)
PROPERTY_WORDS=("casa","appartamento","villa","villetta","trilocale","bilocale","quadrilocale","immobile","terratetto","monolocale","rustico","attico","alloggio","vendita","vendesi","house","property")
PORTAL_HINTS=("immobiliare.it","idealista.it","casa.it","trovacasa.it","wikicasa.it","subito.it","bakeca.it","trovit.it","nestoria.it","gate-away.com","venderecasa.com","tuttocasa.it","tecnocasa.it","tecnorete.it","tempocasa.it","facebook.com")

def now(): return datetime.now(timezone.utc).isoformat()
def clean(s):
    s=re.sub(r"<script\b[^>]*>.*?</script>"," ",s or "",flags=re.I|re.S)
    s=re.sub(r"<style\b[^>]*>.*?</style>"," ",s,flags=re.I|re.S)
    s=re.sub(r"<[^>]+>"," ",s)
    return re.sub(r"\s+"," ",html.unescape(s)).strip()
def fold(s): return clean(s).casefold()
def norm(url):
    p=urlparse(url or ""); q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not(k.lower().startswith("utm_") or k.lower() in TRACK)]
    return urlunparse((p.scheme,p.netloc,p.path,p.params,urlencode(q),""))
def host(url): return urlparse(url or "").netloc.lower().removeprefix("www.")
def portal(url):
    h=host(url); return any(h==d or h.endswith("."+d) for d in PORTAL_HINTS)

def fetch(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,*/*","Accept-Language":"it-IT,it;q=0.9"})
    try:
        with urlopen(req,timeout=TIMEOUT) as r:
            body=r.read(1_200_000).decode(r.headers.get_content_charset() or "utf-8",errors="replace")
            if re.search(r"captcha|verify you are human|access denied|robot check",body,re.I): return False,r.status,"","verifica umana / anti-bot"
            return 200<=r.status<400,r.status,body,""
    except HTTPError as e: return False,e.code,"",str(e)
    except (URLError,TimeoutError,OSError) as e: return False,0,"",str(e)

def addresses(text):
    out=[]; seen=set()
    for m in ADDRESS_RE.finditer(clean(text)):
        v=re.sub(r"\s+"," ",m.group(0)).strip(" ,.;")
        v=re.sub(r",\s*(\d)",r" \1",v)
        k=v.casefold()
        if k not in seen: seen.add(k); out.append(v[:140])
    return out[:12]
def street_of(address):
    s=clean(address).strip(" ,.;")
    s=re.sub(r"\s+\d{1,4}(?:/[A-Za-z0-9]+|[A-Za-z])?\s*$","",s).strip(" ,.;")
    return s
def same_street(address,street): return bool(address and street and street_of(address).casefold()==street.casefold())

def seller_name(raw):
    pats=[
        r'"seller"\s*:\s*\{[^{}]{0,500}?"name"\s*:\s*"([^"]{3,100})"',
        r'"agent"\s*:\s*\{[^{}]{0,500}?"name"\s*:\s*"([^"]{3,100})"',
        r'(?:inserzionista|venditore|proprietario)\s*[:\-]\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ\'’\-]+(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ\'’\-]+){1,3})'
    ]
    for p in pats:
        m=re.search(p,raw or "",re.I|re.S)
        if m:
            v=clean(m.group(1))
            if 3<=len(v)<=100: return v
    return ""
def contacts(text,url,source_type,confidence):
    plain=clean(text); out=[]; seen=set()
    for m in PHONE_RE.finditer(plain):
        v=re.sub(r"\D","",m.group(0))
        if v.startswith("39") and len(v)>=11: v="+"+v
        if not 9<=len(re.sub(r"\D","",v))<=13: continue
        k=("PHONE",v)
        if k not in seen: seen.add(k); out.append({"type":"PHONE","value":v,"source_url":url,"source_type":source_type,"confidence":confidence})
    for m in EMAIL_RE.finditer(plain):
        v=m.group(0).lower(); k=("EMAIL",v)
        if v.endswith((".png",".jpg",".jpeg",".webp",".gif")): continue
        if k not in seen: seen.add(k); out.append({"type":"EMAIL","value":v,"source_url":url,"source_type":source_type,"confidence":confidence})
    return out[:12]
def tokens(text):
    stop={"della","delle","degli","dello","alla","alle","con","per","vendita","casa","appartamento","immobile","villa","torino","euro","privato"}
    return {t for t in re.findall(r"[a-zà-ÿ0-9]{3,}",fold(text)) if t not in stop}
def match_score(item,result,addr):
    a=tokens(f"{item.get('title','')} {item.get('snippet','')}"); b=tokens(f"{result.get('title','')} {result.get('snippet','')}")
    sim=len(a&b)/len(a|b) if a and b else 0; s=int(sim*55)
    target=f"{result.get('title','')} {result.get('snippet','')}"
    if fold(item.get("comune","")) in fold(target): s+=15
    if any(fold(x) in fold(target) for x in addr): s+=30
    return min(s,100)
def dedupe(cs):
    rank={"HIGH":3,"MEDIUM":2,"REVIEW":1}; out={}
    for c in cs:
        k=(c.get("type"),c.get("value"))
        if k not in out or rank.get(c.get("confidence"),0)>rank.get(out[k].get("confidence"),0): out[k]=c
    return list(out.values())

if not ITEM_ID: raise SystemExit("F1_ITEM_ID mancante")
try: state=json.loads(STATE.read_text(encoding="utf-8"))
except Exception as e: raise SystemExit(f"state non leggibile: {e}")
x=(state.get("items") or {}).get(ITEM_ID)
if not x: raise SystemExit(f"item non trovato: {ITEM_ID}")
url=norm(x.get("url","")); comune=(x.get("comune") or "").strip(); title=clean(x.get("title") or "")
private_candidate=(x.get("seller_hint")=="INDIZIO_PRIVATO" or bool(x.get("private_intent"))) and x.get("seller_hint")!="INDIZIO_AGENZIA"
addr=addresses(title); seller=""; public_contacts=[]; listing_fetch={"ok":False,"status":0,"error":""}
if url:
    ok,st,raw,err=fetch(url); listing_fetch={"ok":ok,"status":st,"error":err}
    if ok and raw:
        addr=list(dict.fromkeys(addr+addresses(raw)))[:12]; seller=seller_name(raw)
        if private_candidate: public_contacts+=contacts(raw,url,"LISTING_ORIGINALE","HIGH")

# Query 1: cross-match dello stesso annuncio. Ogni item ha un runner dedicato, quindi non satura il motore.
q1=f'"{title[:110]}" "{comune}"'
results1,error1=search(q1,10); cross=[]; seen=set()
for r in results1:
    u=norm(r.get("url",""))
    if not u or u==url or u in seen: continue
    seen.add(u); ms=match_score(x,r,addr)
    if ms<35: continue
    rec={"url":u,"title":r.get("title",""),"snippet":r.get("snippet",""),"host":host(u),"match_score":ms,"contact_scan":"NOT_SCANNED"}
    addr=list(dict.fromkeys(addr+addresses(r.get("title","")+" "+r.get("snippet",""))))[:12]
    if private_candidate and portal(u) and ms>=55:
        ok2,st2,raw2,err2=fetch(u); rec["contact_scan"]="OK" if ok2 else f"HTTP_{st2 or 0}"
        if ok2 and raw2:
            public_contacts+=contacts(raw2,u,"CROSS_MATCH_IMMOBILE","HIGH" if ms>=75 else "MEDIUM")
            addr=list(dict.fromkeys(addr+addresses(raw2)))[:12]
            if not seller: seller=seller_name(raw2)
    cross.append(rec)
cross=sorted(cross,key=lambda z:z["match_score"],reverse=True)[:12]

street=street_of(addr[0]) if addr else ""; nearby=[]
if street:
    nearby=[a for a in addr if same_street(a,street)]
    # Query 2: stessa via. Solo indirizzi della stessa via vengono mantenuti.
    q2=f'"{street}" "{comune}" (vendita OR casa OR appartamento OR immobile)'
    results2,error2=search(q2,20)
    for r in results2:
        rt=f"{r.get('title','')} {r.get('snippet','')}"
        if not any(w in fold(rt) for w in PROPERTY_WORDS): continue
        for a in addresses(rt):
            if same_street(a,street) and a.casefold() not in {z.casefold() for z in nearby}: nearby.append(a)
else:
    q2=""; error2="nessuna via rilevata"

public_contacts=dedupe(public_contacts)
enrichment={
    "checked_at":now(),"private_candidate":private_candidate,"listing_fetch":listing_fetch,
    "address_hints":addr[:8],"seller_name":seller,"cross_matches":cross,"cross_match_count":len(cross),
    "public_contacts":public_contacts,"contact_ready":any(c.get("confidence") in {"HIGH","MEDIUM"} for c in public_contacts),
    "contact_ready_count":sum(1 for c in public_contacts if c.get("confidence") in {"HIGH","MEDIUM"}),
    "queries":[{"q":q1,"error":error1},{"q":q2,"error":error2}] if q2 else [{"q":q1,"error":error1}]
}
area={"reference_addresses":addr[:8],"street":street,"nearby_public_addresses":nearby[:20]}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps({"item_id":ITEM_ID,"enrichment":enrichment,"area":area},ensure_ascii=False,indent=2),encoding="utf-8")
print(f"ITEM {ITEM_ID} {comune}: via={street or '-'} cross={len(cross)} indirizzi={len(nearby)} contatti={enrichment['contact_ready_count']} q1={error1 or 'OK'} q2={error2 or 'OK'}")
