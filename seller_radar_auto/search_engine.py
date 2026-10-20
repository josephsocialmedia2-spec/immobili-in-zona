#!/usr/bin/env python3
"""Ricerca web best-effort su fonti pubbliche. Nessun bypass di login/CAPTCHA."""
from __future__ import annotations
import html, re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (compatible; F1SellerRadar/1.0; +public-market-research)"

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language":"it-IT,it;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def bing_rss(query, limit=20):
    url = "https://www.bing.com/search?format=rss&q=" + urllib.parse.quote(query)
    try:
        raw = _get(url)
        root = ET.fromstring(raw)
        out=[]
        for item in root.findall(".//item"):
            link=(item.findtext("link") or "").strip()
            title=html.unescape((item.findtext("title") or "").strip())
            desc=html.unescape((item.findtext("description") or "").strip())
            if link:
                out.append({"title":title,"url":link,"snippet":re.sub("<[^>]+>"," ",desc)})
            if len(out)>=limit: break
        return out
    except Exception:
        return []

def duckduckgo_html(query, limit=20):
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        raw=_get(url)
    except Exception:
        return []
    links=re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.I|re.S)
    out=[]
    for href,title in links:
        href=html.unescape(href)
        if "uddg=" in href:
            q=urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href=q.get("uddg",[href])[0]
        title=re.sub("<[^>]+>"," ",html.unescape(title))
        out.append({"title":" ".join(title.split()),"url":href,"snippet":""})
        if len(out)>=limit: break
    return out

def search(query, limit=20, delay=1.0):
    rows=bing_rss(query, limit)
    if not rows:
        time.sleep(delay)
        rows=duckduckgo_html(query, limit)
    return rows
