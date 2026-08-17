#!/usr/bin/env python3
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
TESTS=[
    ("Immobiliare.it","https://www.immobiliare.it/vendita-case/vaie/",r"/annunci/[0-9]+/?"),
    ("Idealista","https://www.idealista.it/vendita-case/vaie-torino/",r"/immobile/[0-9]+/?"),
    ("Casa.it","https://www.casa.it/vendita/residenziale/vaie/",r"/immobili/[0-9]+/?"),
    ("Subito","https://www.subito.it/annunci-piemonte/vendita/immobili/torino/vaie/",r"\.htm$"),
]

class P(HTMLParser):
    def __init__(self): super().__init__(); self.hrefs=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a":
            h=dict(attrs).get("href")
            if h: self.hrefs.append(h)

def fetch(url):
    req=Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml","Accept-Language":"it-IT,it;q=0.9"})
    try:
        with urlopen(req,timeout=20) as r:
            body=r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8",errors="replace")
            return r.status,r.geturl(),body,""
    except HTTPError as e: return e.code,url,"",str(e)
    except (URLError,TimeoutError,OSError) as e: return 0,url,"",str(e)

for label,url,pat in TESTS:
    status,final,body,error=fetch(url)
    print(f"\n### {label} status={status} bytes={len(body)} final={final} error={error}")
    if not body: continue
    print("anti_bot=",bool(re.search(r"captcha|verify you are human|access denied|robot|cloudflare",body,re.I)))
    p=P(); p.feed(body); found=[]
    for href in p.hrefs:
        u=urljoin(final,href)
        if re.search(pat,urlparse(u).path,re.I) and u not in found: found.append(u)
    print("listing_links=",len(found))
    for u in found[:8]: print(" ",u)
