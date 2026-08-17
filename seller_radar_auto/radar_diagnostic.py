#!/usr/bin/env python3
import csv, html, re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
PORTALS = ROOT / "portal_catalog.csv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self._href=None; self._attrs={}; self._text=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower()=="a":
            self._attrs=dict(attrs); self._href=self._attrs.get("href"); self._text=[]
    def handle_data(self, data):
        if self._href is not None: self._text.append(data)
    def handle_endtag(self, tag):
        if tag.lower()=="a" and self._href is not None:
            self.links.append((self._href, re.sub(r"\s+"," ",html.unescape("".join(self._text))).strip(), self._attrs))
            self._href=None; self._text=[]; self._attrs={}

def get(url, data=None):
    req=Request(url, data=data, headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml","Accept-Language":"it-IT,it;q=0.9,en;q=0.5"})
    with urlopen(req,timeout=20) as r:
        return r.read(1_500_000).decode(r.headers.get_content_charset() or "utf-8",errors="replace")

def unwrap_ddg(href):
    if href.startswith("//"): href="https:"+href
    p=urlparse(href)
    if "duckduckgo.com" in p.netloc and p.path.startswith("/l/"):
        qs=parse_qs(p.query)
        if qs.get("uddg"): return unquote(qs["uddg"][0])
    return href

def engine_links(engine, query):
    if engine=="bing_html":
        body=get("https://www.bing.com/search?"+urlencode({"q":query,"count":"10","setlang":"it-IT"}))
        p=LinkParser(); p.feed(body)
        out=[]
        for href,text,attrs in p.links:
            if not href.startswith("http"): continue
            h=urlparse(href).netloc.lower()
            if "bing.com" in h or "microsoft.com" in h: continue
            if text and (href,text) not in [(x[0],x[1]) for x in out]: out.append((href,text))
        return out[:10]
    if engine=="ddg_html":
        data=urlencode({"q":query,"kl":"it-it"}).encode("utf-8")
        body=get("https://html.duckduckgo.com/html/",data=data)
        p=LinkParser(); p.feed(body)
        out=[]
        for href,text,attrs in p.links:
            cls=attrs.get("class","")
            if "result__a" not in cls: continue
            href=unwrap_ddg(href)
            if href.startswith("http"): out.append((href,text))
        return out[:10]
    return []

rows=[]
with PORTALS.open(encoding="utf-8-sig", newline="") as f: rows=list(csv.DictReader(f))
wanted={"Immobiliare.it","Idealista","Casa.it","Tecnocasa"}
for portal in rows:
    if portal.get("label") not in wanted: continue
    q=(portal.get("query_template") or "").replace("{comune}","Vaie")
    print("\n###",portal.get("label"),"QUERY:",q)
    for engine in ("bing_html","ddg_html"):
        print("--",engine)
        try:
            links=engine_links(engine,q)
        except Exception as e:
            print("ERROR",type(e).__name__,str(e)); continue
        if not links: print("NO_RESULTS")
        for i,(u,t) in enumerate(links[:5],1):
            print(f"[{i}] {urlparse(u).netloc} | {t[:100]} | {u}")
