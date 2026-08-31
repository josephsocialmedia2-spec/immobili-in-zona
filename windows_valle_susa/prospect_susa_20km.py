#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 Prospect Susa 20 km — raccolta prudente di contatti PUBBLICATI.

Obiettivo: alimentare la Centrale Telefonate Guidate, non il CRM.
Cerca sul web pubblico attività, imprese e professionisti locali collegabili ai
segnali Radar; conserva telefono/email soltanto sul PC.

Regole:
- nessun login, CAPTCHA bypass, area riservata o data broker;
- niente estrazione di persone fisiche da atti/PDF della PA;
- nessun contatto viene committato o caricato su GitHub;
- ogni riga conserva la URL della fonte pubblica;
- il contatto resta PROSPECT finché una telefonata non produce un esito utile.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RADAR = REPO / "seller_radar_auto"
sys.path.insert(0, str(RADAR))
from search_engine import search  # noqa: E402

CONFIG = RADAR / "f1_microzone_config.json"
WORK_QUEUE = RADAR / "data" / "work_queue.csv"
BUSINESS_PIPELINE = RADAR / "data" / "business_pipeline.csv"
BASE = Path.home() / "Documents" / "F1_Directory_Microzone"
DATA = BASE / "data"
OUT = DATA / "prospect_web_susa_20km.csv"
LOG = BASE / "prospect_web.log"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36 F1Prospect/1.0"
TIMEOUT = 15
MAX_RESULTS_PER_QUERY = 6
MAX_PAGES_PER_TOWN = 14

EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+39[\s.-]*)?(?:0\d{1,3}[\s./-]?\d{5,8}|3\d{2}[\s./-]?\d{6,7})(?!\d)")

EXCLUDED_HOSTS = {
    "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com",
    "linkedin.com", "www.linkedin.com", "x.com", "twitter.com", "tiktok.com",
    "youtube.com", "www.youtube.com",
}
EXCLUDED_EMAIL_PARTS = ("example.", "noreply@", "no-reply@", "privacy@", "abuse@")
COMPETITOR_WORDS = (
    "agenzia immobiliare", "tecnocasa", "tecnorete", "tempocasa", "gabetti",
    "re/max", "remax", "iad immobiliare", "franchising immobiliare",
)
PUBLIC_ADMIN_WORDS = (
    "comune di ", "municipio", "albo pretorio", "amministrazione trasparente",
    "regione piemonte", "città metropolitana", "citta metropolitana", "asl ",
)
BUSINESS_WORDS = (
    "impresa", "azienda", "negozio", "bar", "ristorante", "pizzeria", "hotel",
    "albergo", "b&b", "officina", "carrozzeria", "parrucchiere", "estetista",
    "studio", "geometra", "architetto", "commercialista", "notaio", "condominio",
    "amministratore", "costruzioni", "edile", "artigiano", "locale commerciale",
    "capannone", "ufficio", "attività", "attivita",
)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href") or ""
            self._text = []

    def handle_data(self, data):
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = ""
            self._text = []


def log(message: str) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " | " + message
    print(line)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def clean_text(fragment: str) -> str:
    s = re.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", fragment or "")
    s = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def valid_phone(value: str) -> bool:
    d = digits(value)
    if d.startswith("39") and len(d) > 10:
        d = d[2:]
    if d in {"05526340962", "5526340962"}:
        return False
    return 7 <= len(d) <= 11 and (d.startswith("0") or d.startswith("3"))


def normalize_phone(value: str) -> str:
    d = digits(value)
    if d.startswith("39") and len(d) > 10:
        d = d[2:]
    return d


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def score_value(row: dict) -> int:
    try:
        return int(float(str(row.get("SCORE") or "0").replace(",", ".")))
    except Exception:
        return 0


def load_radar_context(towns: list[str]) -> dict[str, dict]:
    allowed = {x.casefold() for x in towns}
    rows = read_csv(WORK_QUEUE) + read_csv(BUSINESS_PIPELINE)
    out: dict[str, dict] = {}
    for r in rows:
        town = str(r.get("COMUNE") or "").strip()
        if town.casefold() not in allowed:
            continue
        key = town.casefold()
        if key not in out or score_value(r) > score_value(out[key]):
            out[key] = r
    return out


def safe_url(value: str) -> str:
    try:
        p = urllib.parse.urlparse(str(value or "").strip())
    except Exception:
        return ""
    if p.scheme not in {"http", "https"} or not p.netloc:
        return ""
    host = p.netloc.lower().split(":")[0]
    if host in EXCLUDED_HOSTS or p.path.lower().endswith(".pdf"):
        return ""
    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, p.params, p.query, ""))


def fetch_html(url: str) -> str:
    u = safe_url(url)
    if not u:
        return ""
    req = urllib.request.Request(u, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
                return ""
            charset = r.headers.get_content_charset() or "utf-8"
            return r.read(1_200_000).decode(charset, errors="replace")
    except Exception as exc:
        log(f"SKIP pagina {u[:100]}: {exc}")
        return ""


def contact_page(base_url: str, body: str) -> str:
    parser = LinkParser()
    try:
        parser.feed(body)
    except Exception:
        return ""
    host = urllib.parse.urlparse(base_url).netloc.lower()
    for href, text in parser.links:
        blob = (href + " " + text).casefold()
        if not any(k in blob for k in ("contatt", "contact", "chi-siamo", "azienda")):
            continue
        u = urllib.parse.urljoin(base_url, href)
        p = urllib.parse.urlparse(u)
        if p.netloc.lower() == host and safe_url(u) and u != base_url:
            return u
    return ""


def extract_contacts(body: str) -> tuple[list[str], list[str]]:
    text = clean_text(body)
    phones: list[str] = []
    for raw in PHONE_RE.findall(text + " " + body):
        p = normalize_phone(raw)
        if valid_phone(p) and p not in phones:
            phones.append(p)
    emails: list[str] = []
    for raw in EMAIL_RE.findall(text + " " + body):
        e = raw.lower().strip(".,;:()[]<>")
        if any(x in e for x in EXCLUDED_EMAIL_PARTS):
            continue
        if e not in emails:
            emails.append(e)
    return phones[:4], emails[:4]


def category(blob: str) -> str:
    t = blob.casefold()
    if any(x in t for x in ("costruzioni", "impresa edile", "edilizia", "cantiere")):
        return "IMPRESA_EDILE"
    if any(x in t for x in ("amministratore", "condominio")):
        return "AMMINISTRATORE_CONDOMINIO"
    if any(x in t for x in ("geometra", "architetto", "commercialista", "notaio", "studio tecnico")):
        return "PROFESSIONISTA"
    if any(x in t for x in ("cessione", "attività in vendita", "attivita in vendita")):
        return "ATTIVITA_IN_CESSIONE"
    return "ATTIVITA_LOCALE"


def reason(town: str, cat: str, radar: dict) -> str:
    if radar:
        typ = str(radar.get("TIPO_OPPORTUNITA") or "SEgnale immobiliare").strip()
        title = str(radar.get("TITOLO") or radar.get("MOTIVI") or "").strip()
        return f"Incrocio Radar {town}: {typ}" + (f" — {title[:120]}" if title else "")
    reasons = {
        "IMPRESA_EDILE": "Operatore locale: possibile conoscenza di cantieri, immobili o proprietari",
        "AMMINISTRATORE_CONDOMINIO": "Operatore di zona: possibile segnalazione di proprietari/immobili",
        "PROFESSIONISTA": "Professionista locale: possibile segnalazione immobiliare",
        "ATTIVITA_IN_CESSIONE": "Segnale commerciale pubblico: verificare cessione e disponibilità di muri/immobili",
        "ATTIVITA_LOCALE": "Attività locale: verificare disponibilità o conoscenza di immobili/attività in zona",
    }
    return reasons.get(cat, "Prospect pubblico locale da qualificare")


def queries(town: str) -> list[str]:
    return [
        f'"{town}" ("impresa edile" OR geometra OR architetto OR commercialista OR notaio OR "amministratore condominio") (telefono OR email OR contatti)',
        f'"{town}" (bar OR ristorante OR pizzeria OR hotel OR negozio OR officina OR parrucchiere OR estetista OR "attività") (telefono OR email OR contatti)',
        f'"{town}" ("cessione attività" OR "attività in vendita" OR "locale commerciale" OR capannone OR ufficio) (telefono OR email OR contatti)',
    ]


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    towns = [str(x).strip() for x in cfg.get("priority_towns", []) if str(x).strip()]
    if cfg.get("priority_center") != "Susa" or int(cfg.get("priority_radius_km", 0)) != 20:
        raise SystemExit("Prospect engine richiede configurazione Susa 20 km")
    radar_context = load_radar_context(towns)
    rows: list[dict] = []
    seen_contacts: set[str] = set()

    for town in towns:
        pages_done = 0
        seen_urls: set[str] = set()
        radar = radar_context.get(town.casefold(), {})
        for query in queries(town):
            results, err = search(query, MAX_RESULTS_PER_QUERY)
            if err:
                log(f"{town}: {err}")
            for result in results:
                if pages_done >= MAX_PAGES_PER_TOWN:
                    break
                url = safe_url(result.get("url") or "")
                if not url or url in seen_urls:
                    continue
                blob = " ".join([result.get("title") or "", result.get("snippet") or ""])
                low = blob.casefold()
                if any(x in low for x in COMPETITOR_WORDS) or any(x in low for x in PUBLIC_ADMIN_WORDS):
                    continue
                if not any(x in low for x in BUSINESS_WORDS):
                    continue
                seen_urls.add(url)
                pages_done += 1
                body = fetch_html(url)
                if not body:
                    continue
                combined = clean_text(body[:350000]) + " " + blob
                if town.casefold() not in combined.casefold() and town.casefold().replace(" di susa", "") not in combined.casefold():
                    continue
                if any(x in combined.casefold() for x in COMPETITOR_WORDS):
                    continue
                phones, emails = extract_contacts(body)
                if not phones and not emails:
                    cpage = contact_page(url, body)
                    if cpage:
                        cbody = fetch_html(cpage)
                        if cbody:
                            phones, emails = extract_contacts(cbody)
                            if phones or emails:
                                url = cpage
                if not phones and not emails:
                    continue

                cat = category(combined)
                phone = phones[0] if phones else ""
                email = emails[0] if emails else ""
                contact_key = ("p:" + phone) if phone else ("e:" + email)
                if contact_key in seen_contacts:
                    continue
                seen_contacts.add(contact_key)
                base_score = 35 + (12 if phone else 0) + (7 if email else 0)
                radar_score = score_value(radar)
                if radar_score >= 60:
                    base_score += 15
                if cat in {"ATTIVITA_IN_CESSIONE", "IMPRESA_EDILE", "AMMINISTRATORE_CONDOMINIO"}:
                    base_score += 8
                pid = hashlib.sha256(f"{town}|{phone}|{email}|{url}".encode("utf-8")).hexdigest()[:20]
                rows.append({
                    "PROSPECT_ID": pid,
                    "SCORE": min(base_score, 100),
                    "COMUNE": town,
                    "NOME": (result.get("title") or urllib.parse.urlparse(url).netloc)[:180],
                    "CATEGORIA": cat,
                    "TELEFONO": phone,
                    "EMAIL": email,
                    "ALTRI_CONTATTI": " | ".join(phones[1:] + emails[1:]),
                    "MOTIVO_CONTATTO": reason(town, cat, radar),
                    "SEGNALE_RADAR": str(radar.get("TIPO_OPPORTUNITA") or radar.get("SELLER_SIGNAL") or ""),
                    "RADAR_SCORE": radar_score,
                    "RADAR_URL": str(radar.get("URL") or ""),
                    "FONTE_CONTATTO": urllib.parse.urlparse(url).netloc,
                    "URL_CONTATTO": url,
                    "PUBBLICO": "SI",
                    "RPO_STATUS": "DA_VERIFICARE_PRIMA_DEL_CONTATTO",
                    "STATO": "DA_CONTATTARE",
                })
        log(f"{town}: {sum(1 for r in rows if r['COMUNE'] == town)} prospect pubblici")

    rows.sort(key=lambda r: (-int(r["SCORE"]), towns.index(r["COMUNE"]), r["NOME"].casefold()))
    DATA.mkdir(parents=True, exist_ok=True)
    fields = [
        "PROSPECT_ID", "SCORE", "COMUNE", "NOME", "CATEGORIA", "TELEFONO", "EMAIL",
        "ALTRI_CONTATTI", "MOTIVO_CONTATTO", "SEGNALE_RADAR", "RADAR_SCORE", "RADAR_URL",
        "FONTE_CONTATTO", "URL_CONTATTO", "PUBBLICO", "RPO_STATUS", "STATO",
    ]
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    log(f"OK: {len(rows)} prospect pubblici Susa 20 km -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
