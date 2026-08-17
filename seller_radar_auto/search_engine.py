#!/usr/bin/env python3
"""Motore di ricerca pubblico condiviso F1 Seller Radar."""
import html, re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
TIMEOUT = 20

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

def search(query, count=10):
    """Restituisce (results, error). results: [{title,url,snippet}]."""
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
    results=[]; seen=set()
    for href,text,attrs in p.links:
        if "result__a" not in attrs.get("class",""): continue
        url=_unwrap(href)
        if not url.startswith(("http://","https://")): continue
        if "duckduckgo.com/y.js" in url: continue
        if url in seen: continue
        seen.add(url)
        results.append({"title":text,"url":url,"snippet":""})
        if len(results)>=count: break
    return results, ""
