#!/usr/bin/env python3
"""Motore di ricerca pubblico condiviso F1 Seller Radar.

Ordine dei motori:
1. Google Web per le Dork vere richieste dal Radar.
2. DuckDuckGo HTML come fallback.
3. Bing RSS come ultimo fallback.

Non tenta di aggirare CAPTCHA, consent wall o rate limit: se Google blocca la
richiesta, il blocco viene rilevato e il motore passa al fallback successivo.
"""
import html, os, re, time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
TIMEOUT = 20
MIN_INTERVAL = float(os.getenv("F1_SEARCH_INTERVAL", "5"))
RATE_FILE = Path("/tmp/f1_seller_radar_search_rate.txt")

class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self._href=None; self._attrs={}; self._text=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower()=="a":
            self._attrs=dict(attrs); self._href=self._attrs.get("href"); self._text=[]
    def handle_data(self, data):
        if self._href is not None: self._text.append(data)
    def handle_endtag(self, tag):
        if tag.lower()=="a" and self._href is not None:
            text=re.sub(r"\s+"," ",html.unescape("".join(self._text))).strip()
            self.links.append((self._href,text,self._attrs))
            self._href=None; self._attrs={}; self._text=[]

def _plain(fragment):
    s=re.sub(r"<script\b[^>]*>.*?</script>"," ",fragment or "",flags=re.I|re.S)
    s=re.sub(r"<style\b[^>]*>.*?</style>"," ",s,flags=re.I|re.S)
    s=re.sub(r"<[^>]+>"," ",s)
    return re.sub(r"\s+"," ",html.unescape(s)).strip()

def _unwrap_ddg(href):
    if href.startswith("//"): href="https:"+href
    p=urlparse(href)
    if "duckduckgo.com" in p.netloc and p.path.startswith("/l/"):
        qs=parse_qs(p.query)
        if qs.get("uddg"): return unquote(qs["uddg"][0])
    return href

def _unwrap_google(href):
    href=html.unescape(href or "")
    if href.startswith("/url?"):
        qs=parse_qs(urlparse(href).query)
        for k in ("q","url"):
            if qs.get(k): return unquote(qs[k][0])
    if href.startswith("https://www.google.") or href.startswith("https://google."):
        p=urlparse(href)
        if p.path=="/url":
            qs=parse_qs(p.query)
            for k in ("q","url"):
                if qs.get(k): return unquote(qs[k][0])
    return href

def _is_external_google_url(url):
    if not url.startswith(("http://","https://")): return False
    h=urlparse(url).netloc.lower().removeprefix("www.")
    blocked=("google.com","google.it","googleusercontent.com","gstatic.com","youtube.com")
    return not any(h==x or h.endswith("."+x) for x in blocked)

def _rate_limit():
    last=0.0
    try: last=float(RATE_FILE.read_text(encoding="utf-8").strip() or "0")
    except Exception: pass
    wait=MIN_INTERVAL-(time.time()-last)
    if wait>0: time.sleep(wait)
    try: RATE_FILE.write_text(str(time.time()),encoding="utf-8")
    except Exception: pass

def _fetch_text(req, limit=1_800_000):
    with urlopen(req,timeout=TIMEOUT) as r:
        return r.read(limit).decode(r.headers.get_content_charset() or "utf-8",errors="replace")

def _google_search(query, count):
    url="https://www.google.com/search?"+urlencode({
        "q":query,"num":str(min(max(count,10),30)),"hl":"it","gl":"it","filter":"0","pws":"0"
    })
    req=Request(url,headers={
        "User-Agent":UA,
        "Accept":"text/html,application/xhtml+xml",
        "Accept-Language":"it-IT,it;q=0.9,en;q=0.5",
        "Cache-Control":"no-cache",
    })
    try:
        body=_fetch_text(req)
    except HTTPError as e:
        return [], f"Google HTTP {e.code}"
    except (URLError,TimeoutError,OSError) as e:
        return [], f"Google {e}"

    low=body.casefold()
    if any(x in low for x in (
        "our systems have detected unusual traffic",
        "i nostri sistemi hanno rilevato traffico insolito",
        "g-recaptcha",
        "recaptcha/api",
        "sorry/index",
    )):
        return [], "Google CAPTCHA / traffico insolito"
    if "consent.google.com" in low and "before you continue to google" in low:
        return [], "Google consent wall"

    # Google varia spesso markup. Prima identifichiamo gli anchor esterni con
    # testo titolo; poi ricaviamo un frammento vicino al link come snippet.
    p=_Parser()
    try: p.feed(body)
    except Exception: pass
    candidates=[]; seen=set()
    for href,text,attrs in p.links:
        u=_unwrap_google(href or "")
        if not _is_external_google_url(u): continue
        t=re.sub(r"\s+"," ",text or "").strip()
        if not t or len(t)<3: continue
        # I risultati organici hanno quasi sempre h3 nel blocco anchor; quando
        # il parser non conserva i tag, richiediamo comunque un titolo sensato.
        if t.casefold() in {"cached","traduci questa pagina","altre informazioni"}: continue
        if u in seen: continue
        seen.add(u); candidates.append((u,t))

    # Secondo parser, più selettivo: anchor che contiene un H3. È la sorgente
    # preferita e aiuta a eliminare link di navigazione/utility.
    h3=[]
    pat=re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(?:(?!</a>).)*?<h3\b[^>]*>(.*?)</h3>(?:(?!</a>).)*?</a>',re.I|re.S)
    for m in pat.finditer(body):
        u=_unwrap_google(m.group(1)); t=_plain(m.group(2))
        if _is_external_google_url(u) and t and u not in {x[0] for x in h3}: h3.append((u,t,m.start(),m.end()))

    ordered=[]; used=set()
    if h3:
        for idx,(u,t,start,end) in enumerate(h3):
            if u in used: continue
            next_start=h3[idx+1][2] if idx+1<len(h3) else min(len(body),end+3500)
            frag=body[end:min(next_start,end+3500)]
            snippet=_plain(frag)
            # Elimina duplicazioni iniziali del titolo e limita rumore SERP.
            if snippet.startswith(t): snippet=snippet[len(t):].strip(" -·|")
            ordered.append({"title":t,"url":u,"snippet":snippet[:700],"engine":"GOOGLE"}); used.add(u)
            if len(ordered)>=count: break
    else:
        for u,t in candidates:
            if u in used: continue
            # Cerca il link nel markup e prende il testo immediatamente dopo.
            pos=body.find(html.escape(u,quote=True))
            if pos<0: pos=body.find(u)
            frag=body[pos:pos+3200] if pos>=0 else ""
            snippet=_plain(frag)
            if snippet.startswith(t): snippet=snippet[len(t):].strip(" -·|")
            ordered.append({"title":t,"url":u,"snippet":snippet[:700],"engine":"GOOGLE"}); used.add(u)
            if len(ordered)>=count: break

    # Evita di considerare una pagina Google valida se abbiamo soltanto link
    # accidentali di footer/navigazione.
    useful=[r for r in ordered if len(r.get("title","") or "")>=3]
    return useful[:count], "" if useful else "Google: nessun risultato organico parsabile"

def _ddg_search(query, count):
    data=urlencode({"q":query,"kl":"it-it"}).encode("utf-8")
    req=Request("https://html.duckduckgo.com/html/",data=data,headers={
        "User-Agent":UA,
        "Accept":"text/html,application/xhtml+xml",
        "Accept-Language":"it-IT,it;q=0.9,en;q=0.5",
    })
    try:
        body=_fetch_text(req,1_500_000)
    except HTTPError as e:
        return [], f"DDG HTTP {e.code}"
    except (URLError,TimeoutError,OSError) as e:
        return [], f"DDG {e}"
    if re.search(r"captcha|verify you are human|anomaly|rate limit",body,re.I):
        return [], "DDG verifica umana / rate limit"

    p=_Parser(); p.feed(body)
    results=[]; by_url={}; current=None
    for href,text,attrs in p.links:
        cls=attrs.get("class","")
        url=_unwrap_ddg(href or "")
        if not url.startswith(("http://","https://")) or "duckduckgo.com/y.js" in url:
            continue
        if "result__a" in cls:
            if url in by_url:
                current=by_url[url]; continue
            current={"title":text,"url":url,"snippet":"","engine":"DDG"}
            by_url[url]=current; results.append(current)
        elif "result__snippet" in cls and results:
            target=by_url.get(url) or current
            if target and text and not target.get("snippet"): target["snippet"]=text
    return results[:count], ""

def _bing_rss_search(query, count):
    url="https://www.bing.com/search?"+urlencode({"q":query,"format":"rss","count":str(count)})
    req=Request(url,headers={
        "User-Agent":UA,
        "Accept":"application/rss+xml,application/xml,text/xml,*/*",
        "Accept-Language":"it-IT,it;q=0.9",
    })
    try:
        with urlopen(req,timeout=TIMEOUT) as r: body=r.read(900_000)
        root=ET.fromstring(body)
    except HTTPError as e:
        return [], f"Bing HTTP {e.code}"
    except (URLError,TimeoutError,OSError,ET.ParseError) as e:
        return [], f"Bing {e}"
    out=[]; seen=set()
    for n in root.findall(".//item"):
        u=(n.findtext("link") or "").strip()
        if not u.startswith(("http://","https://")) or u in seen: continue
        seen.add(u)
        title=re.sub(r"\s+"," ",html.unescape(n.findtext("title") or "")).strip()
        snippet=re.sub(r"<[^>]+>"," ",n.findtext("description") or "")
        snippet=re.sub(r"\s+"," ",html.unescape(snippet)).strip()
        out.append({"title":title,"url":u,"snippet":snippet,"engine":"BING"})
        if len(out)>=count: break
    return out, ""

def search(query, count=10):
    """Restituisce (results, error), con Google primario e fallback espliciti."""
    errors=[]
    _rate_limit()
    google,err=_google_search(query,count)
    if google: return google,""
    if err: errors.append(err)

    _rate_limit()
    ddg,err=_ddg_search(query,count)
    if ddg: return ddg,""
    if err: errors.append(err)

    _rate_limit()
    bing,err=_bing_rss_search(query,count)
    if bing: return bing,""
    if err: errors.append(err)
    return [], "; ".join(errors)
