#!/usr/bin/env python3
"""Motore di ricerca pubblico condiviso F1 Seller Radar.

Usa DuckDuckGo HTML come motore primario e Bing RSS come fallback quando
DuckDuckGo non restituisce risultati utilizzabili. Non effettua scraping diretto
dei portali e non raccoglie contatti personali.
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

def _unwrap(href):
    if href.startswith("//"): href="https:"+href
    p=urlparse(href)
    if "duckduckgo.com" in p.netloc and p.path.startswith("/l/"):
        qs=parse_qs(p.query)
        if qs.get("uddg"): return unquote(qs["uddg"][0])
    return href

def _rate_limit():
    last=0.0
    try: last=float(RATE_FILE.read_text(encoding="utf-8").strip() or "0")
    except Exception: pass
    wait=MIN_INTERVAL-(time.time()-last)
    if wait>0: time.sleep(wait)
    try: RATE_FILE.write_text(str(time.time()),encoding="utf-8")
    except Exception: pass

def _ddg_search(query, count):
    data=urlencode({"q":query,"kl":"it-it"}).encode("utf-8")
    req=Request("https://html.duckduckgo.com/html/",data=data,headers={
        "User-Agent":UA,
        "Accept":"text/html,application/xhtml+xml",
        "Accept-Language":"it-IT,it;q=0.9,en;q=0.5",
    })
    try:
        with urlopen(req,timeout=TIMEOUT) as r:
            body=r.read(1_500_000).decode(r.headers.get_content_charset() or "utf-8",errors="replace")
    except HTTPError as e:
        return [], f"HTTP {e.code}"
    except (URLError,TimeoutError,OSError) as e:
        return [], str(e)
    if re.search(r"captcha|verify you are human|anomaly|rate limit",body,re.I):
        return [], "verifica umana / rate limit"

    p=_Parser(); p.feed(body)
    results=[]; by_url={}; current=None
    for href,text,attrs in p.links:
        cls=attrs.get("class","")
        url=_unwrap(href or "")
        if not url.startswith(("http://","https://")) or "duckduckgo.com/y.js" in url:
            continue
        if "result__a" in cls:
            if url in by_url:
                current=by_url[url]
                continue
            current={"title":text,"url":url,"snippet":""}
            by_url[url]=current; results.append(current)
        elif "result__snippet" in cls and results:
            target=by_url.get(url) or current
            if target and text and not target.get("snippet"):
                target["snippet"]=text
    return results[:count], ""

def _bing_rss_search(query, count):
    url="https://www.bing.com/search?"+urlencode({"q":query,"format":"rss","count":str(count)})
    req=Request(url,headers={
        "User-Agent":UA,
        "Accept":"application/rss+xml,application/xml,text/xml,*/*",
        "Accept-Language":"it-IT,it;q=0.9",
    })
    try:
        with urlopen(req,timeout=TIMEOUT) as r:
            body=r.read(900_000)
        root=ET.fromstring(body)
    except HTTPError as e:
        return [], f"Bing HTTP {e.code}"
    except (URLError,TimeoutError,OSError,ET.ParseError) as e:
        return [], f"Bing {e}"
    out=[]; seen=set()
    for n in root.findall(".//item"):
        u=(n.findtext("link") or "").strip()
        if not u.startswith(("http://","https://")) or u in seen:
            continue
        seen.add(u)
        title=re.sub(r"\s+"," ",html.unescape(n.findtext("title") or "")).strip()
        snippet=re.sub(r"<[^>]+>"," ",n.findtext("description") or "")
        snippet=re.sub(r"\s+"," ",html.unescape(snippet)).strip()
        out.append({"title":title,"url":u,"snippet":snippet})
        if len(out)>=count: break
    return out, ""

def search(query, count=10):
    """Restituisce (results, error), con risultati deduplicati e snippet."""
    _rate_limit()
    ddg, ddg_error=_ddg_search(query,count)
    if ddg:
        return ddg, ""

    # Fallback soltanto se DDG non produce risultati: evita doppie richieste inutili.
    _rate_limit()
    bing, bing_error=_bing_rss_search(query,count)
    if bing:
        # Il fallback ha prodotto risultati validi: la sorgente è operativa.
        return bing, ""
    err="; ".join(x for x in (ddg_error,bing_error) if x)
    return [], err
