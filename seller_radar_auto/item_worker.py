#!/usr/bin/env python3
"""Worker isolato per un annuncio: cross-match, indirizzo, prezzo, inserzionista e radar della stessa via."""
import html, json, os, re
from collections import Counter
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
ADDRESS_RE=re.compile(r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo|localit[aà])\s+[A-Za-zÀ-ÿ0-9'’.\-\s,]{2,80}?[,\s]+\d{1,4}(?:/[A-Za-z0-9]+|[A-Za-z])?\b",re.I)
PROPERTY_WORDS=("casa","appartamento","villa","villetta","trilocale","bilocale","quadrilocale","immobile","terratetto","monolocale","rustico","attico","alloggio","vendita","vendesi","house","property")
PORTAL_HINTS=("immobiliare.it","idealista.it","casa.it","trovacasa.it","wikicasa.it","subito.it","bakeca.it","trovit.it","nestoria.it","gate-away.com","venderecasa.com","tuttocasa.it","tecnocasa.it","tecnorete.it","tempocasa.it","facebook.com")
PORTAL_NAMES={"immobiliare.it","idealista","idealista.it","casa.it","trovacasa","wikicasa","subito","bakeca","trovit","nestoria","gate-away","facebook","tecnocasa","tecnorete","tempocasa","gabetti","remax","re/max"}
BAD_PRICE_CONTEXT=("spese condominiali","spese mensili","al mese","/mese","mese","rata","mutuo","caparra","cauzione","provvigione","commissione","condominio","spese annue")

def now(): return datetime.now(timezone.utc).isoformat()
def clean(s):
    s=re.sub(r"<script\b[^>]*>.*?</script>"," ",s or "",flags=re.I|re.S); s=re.sub(r"<style\b[^>]*>.*?</style>"," ",s,flags=re.I|re.S); s=re.sub(r"<[^>]+>"," ",s)
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
            body=r.read(1_500_000).decode(r.headers.get_content_charset() or "utf-8",errors="replace")
            if re.search(r"captcha|verify you are human|access denied|robot check",body,re.I): return False,r.status,"","verifica umana / anti-bot"
            return 200<=r.status<400,r.status,body,""
    except HTTPError as e: return False,e.code,"",str(e)
    except (URLError,TimeoutError,OSError) as e: return False,0,"",str(e)

def addresses(text):
    out=[]; seen=set()
    for m in ADDRESS_RE.finditer(clean(text)):
        v=re.sub(r"\s+"," ",m.group(0)).strip(" ,.;"); v=re.sub(r",\s*(\d)",r" \1",v); k=v.casefold()
        if k not in seen: seen.add(k); out.append(v[:140])
    return out[:12]
def street_of(address):
    s=clean(address).strip(" ,.;"); return re.sub(r"\s+\d{1,4}(?:/[A-Za-z0-9]+|[A-Za-z])?\s*$","",s).strip(" ,.;")
def same_street(address,street): return bool(address and street and street_of(address).casefold()==street.casefold())

def parse_amount(v):
    if v is None:return None
    s=str(v).strip().replace("€","").replace("EUR","").replace("eur","").replace(" ","")
    if not s:return None
    if re.fullmatch(r"\d+[.,]\d{2}",s): s=re.split(r"[.,]",s)[0]
    if "," in s and "." in s:
        if s.rfind(",")>s.rfind("."): s=s.replace(".","").split(",",1)[0]
        else: s=s.replace(",","").split(".",1)[0]
    elif "," in s:
        p=s.split(","); s="".join(p) if all(len(x)==3 for x in p[1:]) else p[0]
    elif "." in s:
        p=s.split("."); s="".join(p) if all(len(x)==3 for x in p[1:]) else p[0]
    d=re.sub(r"\D","",s)
    if not d:return None
    n=int(d); return n if 5000<=n<=20_000_000 else None

def price_candidates(raw,title="",snippet=""):
    out=[]
    def add(value,score,source,context=""):
        n=parse_amount(value)
        if not n:return
        if any(w in fold(context) for w in BAD_PRICE_CONTEXT): score-=70
        if score>=25: out.append({"value":n,"score":score,"source":source,"context":clean(context)[:180]})
    if raw:
        for pat,score,src in [(r'"price"\s*:\s*"?([0-9][0-9.,\s]{3,14})"?',100,"JSON_PRICE"),(r'itemprop=["\']price["\'][^>]{0,180}?content=["\']([^"\']+)',98,"ITEMPROP_PRICE"),(r'property=["\']product:price:amount["\'][^>]{0,180}?content=["\']([^"\']+)',98,"META_PRODUCT_PRICE"),(r'name=["\']price["\'][^>]{0,180}?content=["\']([^"\']+)',92,"META_PRICE"),(r'"priceValue"\s*:\s*"?([0-9][0-9.,\s]{3,14})"?',95,"JSON_PRICE_VALUE")]:
            for m in re.finditer(pat,raw,re.I|re.S): add(m.group(1),score,src,m.group(0))
        plain=clean(raw)
        for m in re.finditer(r'(?:€|EUR\b|euro\b)\s*([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})(?:[,.]00)?|([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})(?:[,.]00)?\s*(?:€|EUR\b|euro\b)',plain,re.I):
            a=max(0,m.start()-70); b=min(len(plain),m.end()+70); add(m.group(1) or m.group(2),55,"BODY_TEXT",plain[a:b])
    for label,text,score in (("TITLE",title,88),("SNIPPET",snippet,78)):
        for m in re.finditer(r'(?:€|EUR\b|euro\b)\s*([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})|([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})\s*(?:€|EUR\b|euro\b)',text or "",re.I): add(m.group(1) or m.group(2),score,label,text)
    return out
def best_price(raw,title="",snippet=""):
    c=price_candidates(raw,title,snippet)
    if not c:return {"value":None,"confidence":"NONE","source":"","evidence_count":0}
    by=Counter(x["value"] for x in c)
    for x in c:x["score"]+=min(20,(by[x["value"]]-1)*5)
    c.sort(key=lambda x:(x["score"],by[x["value"]]),reverse=True); b=c[0]; conf="HIGH" if b["score"]>=90 else "MEDIUM" if b["score"]>=65 else "REVIEW"
    return {"value":b["value"],"confidence":conf,"source":b["source"],"evidence_count":by[b["value"]],"context":b.get("context","")}

def valid_seller(v):
    v=clean(v).strip(" -|,.;:"); low=v.casefold()
    if not 3<=len(v)<=120 or low in PORTAL_NAMES:return ""
    if any(x in low for x in ("privacy","cookie","assistenza","servizio clienti","immobile in vendita","annuncio","contatta l'inserzionista")):return ""
    return "" if re.fullmatch(r"[0-9 .,+-]+",v) else v
def seller_name(raw,fallback_text=""):
    found=[]
    for p,score,src in [(r'"seller"\s*:\s*\{[^{}]{0,900}?"name"\s*:\s*"([^"]{3,120})"',100,"JSON_SELLER"),(r'"agent"\s*:\s*\{[^{}]{0,900}?"name"\s*:\s*"([^"]{3,120})"',100,"JSON_AGENT"),(r'"realEstateAgent"\s*:\s*\{[^{}]{0,900}?"name"\s*:\s*"([^"]{3,120})"',100,"JSON_RE_AGENT"),(r'"provider"\s*:\s*\{[^{}]{0,900}?"name"\s*:\s*"([^"]{3,120})"',90,"JSON_PROVIDER"),(r'"brand"\s*:\s*\{[^{}]{0,700}?"name"\s*:\s*"([^"]{3,120})"',72,"JSON_BRAND"),(r'(?:agenzia|inserzionista|venditore|professionista)\s*[:\-]\s*([^|<>\n\r]{3,120})',78,"VISIBLE_LABEL")]:
        for m in re.finditer(p,raw or "",re.I|re.S):
            v=valid_seller(m.group(1));
            if v:found.append((score,v,src))
    text=clean(fallback_text)
    m=re.search(r'\bAgenzia\s+([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9&\'’ .\-]{2,90})',text,re.I)
    if m:
        v=valid_seller(m.group(1));
        if v:found.append((66,v,"SNIPPET_AGENCY"))
    m=re.search(r'\b(Tempocasa|Tecnocasa|Tecnorete|Gabetti|RE/?MAX)(?:\s+[A-Za-zÀ-ÿ0-9&\'’ .\-]{0,70})?',text,re.I)
    if m:
        v=valid_seller(m.group(0));
        if v:found.append((60,v,"BRAND_HINT"))
    if not found:return {"name":"","confidence":"NONE","source":""}
    found.sort(key=lambda z:(z[0],len(z[1])),reverse=True); score,v,src=found[0]
    return {"name":v,"confidence":"HIGH" if score>=90 else "MEDIUM" if score>=70 else "REVIEW","source":src}

def contacts(text,url,source_type,confidence):
    plain=clean(text); out=[]; seen=set()
    for m in PHONE_RE.finditer(plain):
        v=re.sub(r"\D","",m.group(0)); v="+"+v if v.startswith("39") and len(v)>=11 else v
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
    a=tokens(f"{item.get('title','')} {item.get('snippet','')}"); b=tokens(f"{result.get('title','')} {result.get('snippet','')}"); sim=len(a&b)/len(a|b) if a and b else 0; s=int(sim*55); target=f"{result.get('title','')} {result.get('snippet','')}"
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
url=norm(x.get("url","")); comune=(x.get("comune") or "").strip(); title=clean(x.get("title") or ""); snippet=clean(x.get("snippet") or "")
private_candidate=(x.get("seller_hint")=="INDIZIO_PRIVATO" or bool(x.get("private_intent"))) and x.get("seller_hint")!="INDIZIO_AGENZIA"
addr=addresses(f"{title} {snippet}"); seller_info={"name":"","confidence":"NONE","source":""}; price_info=best_price("",title,snippet); public_contacts=[]; listing_fetch={"ok":False,"status":0,"error":""}
if url:
    ok,st,raw,err=fetch(url); listing_fetch={"ok":ok,"status":st,"error":err}
    if ok and raw:
        addr=list(dict.fromkeys(addr+addresses(raw)))[:12]; seller_info=seller_name(raw,f"{title} {snippet}"); price_info=best_price(raw,title,snippet)
        if private_candidate: public_contacts+=contacts(raw,url,"LISTING_ORIGINALE","HIGH")

q1=f'"{title[:110]}" "{comune}"'; results1,error1=search(q1,10); cross=[]; seen=set()
for r in results1:
    u=norm(r.get("url",""))
    if not u or u==url or u in seen: continue
    seen.add(u); ms=match_score(x,r,addr)
    if ms<35: continue
    rt=f"{r.get('title','')} {r.get('snippet','')}"; rec={"url":u,"title":r.get("title",""),"snippet":r.get("snippet",""),"host":host(u),"match_score":ms,"contact_scan":"NOT_SCANNED"}
    rp=best_price("",r.get("title",""),r.get("snippet","")); rec["detected_price"]=rp.get("value"); rec["price_confidence"]=rp.get("confidence"); addr=list(dict.fromkeys(addr+addresses(rt)))[:12]
    if not seller_info.get("name"):
        si=seller_name("",rt)
        if si.get("name"): seller_info=si
    if (not price_info.get("value") or price_info.get("confidence") in {"NONE","REVIEW"}) and rp.get("value") and rp.get("confidence") in {"HIGH","MEDIUM"}: price_info=rp
    if private_candidate and portal(u) and ms>=55:
        ok2,st2,raw2,err2=fetch(u); rec["contact_scan"]="OK" if ok2 else f"HTTP_{st2 or 0}"
        if ok2 and raw2:
            public_contacts+=contacts(raw2,u,"CROSS_MATCH_IMMOBILE","HIGH" if ms>=75 else "MEDIUM"); addr=list(dict.fromkeys(addr+addresses(raw2)))[:12]
            if not seller_info.get("name"):
                si=seller_name(raw2,rt)
                if si.get("name"): seller_info=si
            if not price_info.get("value"):
                rp2=best_price(raw2,r.get("title",""),r.get("snippet",""))
                if rp2.get("value"): price_info=rp2
    cross.append(rec)
cross=sorted(cross,key=lambda z:z["match_score"],reverse=True)[:12]

street=street_of(addr[0]) if addr else ""; nearby=[]
if street:
    nearby=[a for a in addr if same_street(a,street)]; q2=f'"{street}" "{comune}" (vendita OR casa OR appartamento OR immobile)'; results2,error2=search(q2,20)
    for r in results2:
        rt=f"{r.get('title','')} {r.get('snippet','')}"
        if not any(w in fold(rt) for w in PROPERTY_WORDS): continue
        for a in addresses(rt):
            if same_street(a,street) and a.casefold() not in {z.casefold() for z in nearby}: nearby.append(a)
else:q2=""; error2="nessuna via rilevata"

public_contacts=dedupe(public_contacts)
enrichment={"checked_at":now(),"private_candidate":private_candidate,"listing_fetch":listing_fetch,"address_hints":addr[:8],"seller_name":seller_info.get("name","") ,"seller_confidence":seller_info.get("confidence","NONE"),"seller_source":seller_info.get("source",""),"detected_price":price_info.get("value"),"price_confidence":price_info.get("confidence","NONE"),"price_source":price_info.get("source",""),"price_evidence_count":price_info.get("evidence_count",0),"cross_matches":cross,"cross_match_count":len(cross),"public_contacts":public_contacts,"contact_ready":any(c.get("confidence") in {"HIGH","MEDIUM"} for c in public_contacts),"contact_ready_count":sum(1 for c in public_contacts if c.get("confidence") in {"HIGH","MEDIUM"}),"queries":[{"q":q1,"error":error1},{"q":q2,"error":error2}] if q2 else [{"q":q1,"error":error1}]}
area={"reference_addresses":addr[:8],"street":street,"nearby_public_addresses":nearby[:20]}
OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps({"item_id":ITEM_ID,"enrichment":enrichment,"area":area},ensure_ascii=False,indent=2),encoding="utf-8")
print(f"ITEM {ITEM_ID} {comune}: via={street or '-'} prezzo={price_info.get('value') or '-'}({price_info.get('confidence')}) seller={seller_info.get('name') or '-'}({seller_info.get('confidence')}) cross={len(cross)} indirizzi={len(nearby)} contatti={enrichment['contact_ready_count']} q1={error1 or 'OK'} q2={error2 or 'OK'}")
