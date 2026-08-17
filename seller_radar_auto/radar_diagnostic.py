#!/usr/bin/env python3
import time
from urllib.parse import urlparse
from search_engine import search

PORTAL_DOMAINS=(
    "immobiliare.it","idealista.it","casa.it","subito.it","trovacasa.it","wikicasa.it",
    "tecnocasa.it","tecnorete.it","tempocasa.it","trovit.it","tuttocasa.it","venderecasa.com"
)
COMUNI=["Avigliana","Vaie","Condove","Susa"]

for idx,comune in enumerate(COMUNI,1):
    # Una query unica per comune: lascia al motore la scelta dei portali, poi classifichiamo per dominio.
    q=f'"{comune}" (vendita OR "in vendita") (casa OR appartamento OR villa)'
    results,error=search(q,30)
    useful=[]
    for r in results:
        h=urlparse(r.get("url","")).netloc.lower().removeprefix("www.")
        if any(h==d or h.endswith("."+d) for d in PORTAL_DOMAINS):
            useful.append(r)
    print(f"\n[{idx}] {comune}: raw={len(results)} useful={len(useful)} error={error or '-'}")
    for r in useful[:8]: print(" ",urlparse(r['url']).netloc,"|",r['title'][:100],"|",r['url'])
    if idx < len(COMUNI): time.sleep(5)
