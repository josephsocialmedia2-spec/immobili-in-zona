#!/usr/bin/env python3
import csv, html, re, xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
PORTALS = ROOT / "portal_catalog.csv"
UA = "F1RadarDiagnostic/1.0"
PROPERTY_WORDS = ("casa","appartamento","villa","villetta","trilocale","bilocale","quadrilocale","immobile","terratetto","monolocale","rustico","attico","alloggio","vendita","vendesi","house","property")
SALE_WORDS = ("vendita","vendesi","vende","in vendita","€","euro","for sale")

def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def fold(s): return clean(s).casefold()

def host_matches(host, expected):
    host=(host or "").lower().split(":")[0]; expected=(expected or "").lower().strip()
    if not expected: return True
    if expected.startswith("*."): return host.endswith(expected[1:])
    return host == expected or host.removeprefix("www.") == expected.removeprefix("www.")

def reasons(url,title,desc,comune,domain,path_regex):
    out=[]; p=urlparse(url); t=fold(f"{title} {desc}"); c=fold(comune)
    if not host_matches(p.netloc,domain): out.append(f"DOMAIN({p.netloc}!={domain})")
    if path_regex and not re.search(path_regex,p.path,re.I): out.append(f"PATH({p.path}!~{path_regex})")
    if c and c not in t and c.replace(" ","-") not in url.casefold(): out.append("COMUNE")
    if not any(w in t for w in PROPERTY_WORDS): out.append("PROPERTY_WORD")
    if not any(w in t for w in SALE_WORDS): out.append("SALE_WORD")
    return out or ["ACCEPT"]

rows=[]
with PORTALS.open(encoding="utf-8-sig", newline="") as f:
    rows=list(csv.DictReader(f))

wanted={"Immobiliare.it","Idealista","Casa.it","Web generale","Tecnocasa"}
for portal in rows:
    if portal.get("label") not in wanted: continue
    comune="Vaie"
    q=(portal.get("query_template") or "").replace("{comune}",comune)
    url="https://www.bing.com/search?"+urlencode({"q":q,"format":"rss","count":"10"})
    req=Request(url,headers={"User-Agent":UA,"Accept":"application/rss+xml,application/xml,text/xml,*/*","Accept-Language":"it-IT,it;q=0.9"})
    with urlopen(req,timeout=20) as r:
        body=r.read(900000).decode(r.headers.get_content_charset() or "utf-8",errors="replace")
    root=ET.fromstring(body)
    print("\n###",portal.get("label"),"QUERY:",q)
    for i,n in enumerate(root.findall(".//item")[:5],1):
        title=clean(n.findtext("title") or "")
        link=(n.findtext("link") or "").strip()
        desc=clean(n.findtext("description") or "")
        rs=reasons(link,title,desc,comune,(portal.get("domain") or "").strip(),(portal.get("path_regex") or "").strip())
        print(f"[{i}] {rs} | {title[:120]} | {link}")
