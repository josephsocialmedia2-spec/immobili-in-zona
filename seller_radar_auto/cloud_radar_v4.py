#!/usr/bin/env python3
import csv, hashlib, html, json, re, time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"; DATA.mkdir(parents=True, exist_ok=True)
MUNICIPALITIES = ROOT / "municipalities.csv"
PORTALS = ROOT / "portal_catalog.csv"
STATE = DATA / "state.json"
QUEUE = DATA / "work_queue.csv"
STATUS = DATA / "source_status.csv"
DASH = ROOT / "dashboard.html"

UA = "F1SellerRadar/4.0 (+public-index-monitor; no-contact-harvesting)"
TIMEOUT = 20
TRACK = {"gclid", "fbclid", "msclkid", "ref", "source"}
PROPERTY_WORDS = (
    "casa","appartamento","villa","villetta","trilocale","bilocale","quadrilocale",
    "immobile","terratetto","monolocale","rustico","attico","alloggio","vendita",
    "vendesi","house","property"
)
SALE_WORDS = ("vendita","vendesi","vende","in vendita","€","euro","for sale")

def now():
    return datetime.now(timezone.utc).isoformat()

def key(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:20]

def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def fold(s):
    return clean(s).casefold()

def norm(url):
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not (k.lower().startswith("utm_") or k.lower() in TRACK)]
    return urlunparse((p.scheme, p.netloc, p.path, p.params, urlencode(q), ""))

def host_matches(host, expected):
    host = (host or "").lower().split(":")[0]
    expected = (expected or "").lower().strip()
    if not expected:
        return True
    if expected.startswith("*."):
        suffix = expected[1:]
        return host.endswith(suffix)
    if host == expected:
        return True
    return host.removeprefix("www.") == expected.removeprefix("www.")

def fetch(url):
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml,application/xml,text/xml,*/*",
        "Accept-Language": "it-IT,it;q=0.9",
    })
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(900_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
            if re.search(r"captcha|verify you are human|access denied", body, re.I):
                return False, 0, "", "verifica umana / anti-bot"
            return 200 <= r.status < 400, r.status, body, ""
    except HTTPError as e:
        return False, e.code, "", str(e)
    except (URLError, TimeoutError, OSError) as e:
        return False, 0, "", str(e)

def price(text):
    for pat in [
        r"€\s*([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})",
        r"([0-9]{1,3}(?:[.\s][0-9]{3})+|[0-9]{4,8})\s*€",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            n = int(re.sub(r"\D", "", m.group(1)))
            if 5_000 <= n <= 20_000_000:
                return n
    return None

def seller_hint(text):
    t = fold(text)
    if re.search(r"\b(no agenzie|senza agenzia|da privato|annuncio privato|inserzionista privato|vendita privata|privato vende|vendo privatamente|solo privati)\b", t, re.I):
        return "INDIZIO_PRIVATO"
    if re.search(r"\b(agenzia immobiliare|tecnocasa|tecnorete|tempocasa|gabetti|re/?max|franchising immobiliare)\b", t, re.I):
        return "INDIZIO_AGENZIA"
    return "NON_DETERMINATO"

def relevant(url, title, desc, comune, domain, path_regex):
    p = urlparse(url)
    if not host_matches(p.netloc, domain):
        return False
    if path_regex and not re.search(path_regex, p.path, re.I):
        return False
    t = fold(f"{title} {desc}")
    c = fold(comune)
    if c and c not in t and c.replace(" ", "-") not in url.casefold():
        return False
    if not any(w in t for w in PROPERTY_WORDS):
        return False
    if not any(w in t for w in SALE_WORDS):
        return False
    return True

def drops(hist):
    return sum(
        1 for a, b in zip(hist, hist[1:])
        if a.get("price") and b.get("price") and b["price"] < a["price"]
    )

def score(x):
    s, why = 15, []
    if x.get("lifecycle") == "NEW":
        s += 15; why.append("nuova rilevazione")
    if x.get("private_intent"):
        s += 12; why.append("fonte/query orientata ai privati")
    if x.get("seller_hint") == "INDIZIO_PRIVATO":
        s += 28; why.append("indizio privato/no agenzie")
    if x.get("seller_hint") == "INDIZIO_AGENZIA":
        s -= 12; why.append("indizio agenzia")
    if x.get("price_history"):
        s += 5; why.append("prezzo rilevato")
    d = drops(x.get("price_history", []))
    if d:
        s += 18; why.append("ribasso rilevato")
    if d >= 2:
        s += 10; why.append("ribassi multipli")
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(x["first_seen"])).days
        if age >= 30:
            s += 8; why.append("30+ giorni monitorati")
        if age >= 60:
            s += 8; why.append("60+ giorni monitorati")
    except Exception:
        pass
    return max(0, min(100, s)), why or ["monitoraggio base"]

def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

municipalities = [r["comune"].strip() for r in load_csv(MUNICIPALITIES)
                  if r.get("enabled") == "1" and r.get("comune")]
portals = [r for r in load_csv(PORTALS)
           if r.get("enabled") == "1" and r.get("query_template")]

state = {"items": {}, "sources": {}}
if STATE.exists():
    try:
        state.update(json.loads(STATE.read_text(encoding="utf-8")))
    except Exception:
        pass

items = state.setdefault("items", {})
sources_state = {}

for comune in municipalities:
    for portal in portals:
        label = portal["label"].strip()
        domain = (portal.get("domain") or "").strip()
        path_regex = (portal.get("path_regex") or "").strip()
        private_intent = portal.get("private_intent") == "1"
        max_results = int(portal.get("max_results") or 10)
        query = portal["query_template"].replace("{comune}", comune)
        qkey = "search:" + key(comune + "|" + label + "|" + query)

        rss = "https://www.bing.com/search?" + urlencode({
            "q": query,
            "format": "rss",
            "count": str(max_results),
        })
        ok, status, body, error = fetch(rss)
        if not ok:
            sources_state[qkey] = {
                "fonte": label, "comune": comune, "last_check": now(),
                "status": "ERROR", "message": f"HTTP {status} {error}".strip(),
                "raw_results": 0, "accepted": 0, "seed_url": rss,
            }
            continue

        try:
            root = ET.fromstring(body)
            nodes = root.findall(".//item")
        except ET.ParseError as e:
            sources_state[qkey] = {
                "fonte": label, "comune": comune, "last_check": now(),
                "status": "ERROR", "message": f"RSS non valido: {e}",
                "raw_results": 0, "accepted": 0, "seed_url": rss,
            }
            continue

        accepted = 0
        for n in nodes[:max_results]:
            title = clean(n.findtext("title") or "")
            url = norm((n.findtext("link") or "").strip())
            desc = clean(n.findtext("description") or "")
            if not url.startswith(("http://", "https://")):
                continue
            if not relevant(url, title, desc, comune, domain, path_regex):
                continue

            i = key(url)
            p = price(f"{title} {desc}")
            hint = seller_hint(f"{title} {desc}")
            if i not in items:
                items[i] = {
                    "id": i, "comune": comune, "fonte": label, "url": url,
                    "title": title[:220], "snippet": desc[:500],
                    "price_history": [], "seller_hint": hint,
                    "private_intent": private_intent,
                    "first_seen": now(), "last_seen": now(),
                    "checks": 1, "lifecycle": "NEW",
                    "domain_rule": domain, "path_rule": path_regex,
                }
            else:
                x = items[i]
                x["last_seen"] = now()
                x["checks"] = int(x.get("checks", 0)) + 1
                x["title"] = title[:220] or x.get("title", "")
                x["snippet"] = desc[:500]
                x["private_intent"] = x.get("private_intent", False) or private_intent
                x["fonte"] = x.get("fonte") or label
                x["domain_rule"] = x.get("domain_rule") or domain
                x["path_rule"] = x.get("path_rule") or path_regex
                if hint != "NON_DETERMINATO":
                    x["seller_hint"] = hint
                if x.get("lifecycle") == "NEW" and x["checks"] > 1:
                    x["lifecycle"] = "TRACKED"

            if p:
                hist = items[i].setdefault("price_history", [])
                if not hist or hist[-1]["price"] != p:
                    hist.append({"at": now(), "price": p})
                    items[i]["price_history"] = hist[-20:]
            accepted += 1

        sources_state[qkey] = {
            "fonte": label, "comune": comune, "last_check": now(),
            "status": "OK", "message": "", "raw_results": len(nodes),
            "accepted": accepted, "seed_url": rss,
        }
        time.sleep(0.35)

for x in items.values():
    x["score"], x["score_reasons"] = score(x)

STATE.write_text(json.dumps(
    {"updated_at": now(), "items": items, "sources": sources_state},
    ensure_ascii=False, indent=2
), encoding="utf-8")

fields = [
    "PRIORITA","SCORE","COMUNE","FONTE","TITOLO","PREZZO","PREZZO_PRECEDENTE",
    "RIBASSI","INDIZIO_INSERZIONISTA","STATO","PRIMA_RILEVAZIONE",
    "ULTIMO_CONTROLLO","MOTIVI","URL"
]
queue = []
for x in sorted(items.values(), key=lambda z: z.get("score", 0), reverse=True):
    hist = x.get("price_history", [])
    queue.append({
        "PRIORITA": "ALTA" if x["score"] >= 70 else "MEDIA" if x["score"] >= 45 else "BASSA",
        "SCORE": x["score"], "COMUNE": x.get("comune", ""), "FONTE": x.get("fonte", ""),
        "TITOLO": x.get("title", ""), "PREZZO": hist[-1]["price"] if hist else "",
        "PREZZO_PRECEDENTE": hist[-2]["price"] if len(hist) > 1 else "",
        "RIBASSI": drops(hist), "INDIZIO_INSERZIONISTA": x.get("seller_hint", "NON_DETERMINATO"),
        "STATO": x.get("lifecycle", ""), "PRIMA_RILEVAZIONE": x.get("first_seen", ""),
        "ULTIMO_CONTROLLO": x.get("last_seen", ""),
        "MOTIVI": " | ".join(x.get("score_reasons", [])), "URL": x.get("url", ""),
    })

with QUEUE.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(queue)

status_fields = [
    "FONTE","COMUNE","STATO","ULTIMO_CONTROLLO","RISULTATI_GREZZI",
    "ACCETTATI","MESSAGGIO","URL_SORGENTE"
]
status_rows = [{
    "FONTE": s.get("fonte", ""), "COMUNE": s.get("comune", ""),
    "STATO": s.get("status", ""), "ULTIMO_CONTROLLO": s.get("last_check", ""),
    "RISULTATI_GREZZI": s.get("raw_results", 0), "ACCETTATI": s.get("accepted", 0),
    "MESSAGGIO": s.get("message", ""), "URL_SORGENTE": s.get("seed_url", ""),
} for s in sources_state.values()]

with STATUS.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=status_fields); w.writeheader(); w.writerows(status_rows)

def euro(v):
    return "—" if not v else f"€ {int(v):,}".replace(",", ".")

high = sum(1 for r in queue if int(r["SCORE"]) >= 70)
priv = sum(1 for r in queue if r["INDIZIO_INSERZIONISTA"] == "INDIZIO_PRIVATO")
ok_count = sum(1 for r in status_rows if r["STATO"] == "OK")
accepted_total = sum(int(r["ACCETTATI"] or 0) for r in status_rows)
portal_names = sorted({r["FONTE"] for r in status_rows})

trs = []
for r in queue:
    cls = "high" if r["SCORE"] >= 70 else "med" if r["SCORE"] >= 45 else "low"
    trs.append(
        f"<tr data-comune='{html.escape(r['COMUNE'])}' data-fonte='{html.escape(r['FONTE'])}'>"
        f"<td><span class='score {cls}'>{r['SCORE']}</span></td>"
        f"<td>{html.escape(r['PRIORITA'])}</td>"
        f"<td>{html.escape(r['COMUNE'])}</td>"
        f"<td>{html.escape(r['FONTE'])}</td>"
        f"<td>{html.escape(r['INDIZIO_INSERZIONISTA'])}</td>"
        f"<td>{html.escape(r['TITOLO'])}</td>"
        f"<td>{euro(r['PREZZO'])}</td>"
        f"<td>{r['RIBASSI']}</td>"
        f"<td>{html.escape(r['MOTIVI'])}</td>"
        f"<td><a href='{html.escape(r['URL'])}' target='_blank' rel='noopener'>APRI FONTE</a></td>"
        f"</tr>"
    )
if not trs:
    trs = ["<tr><td colspan='10'>Nessun risultato immobiliare ha superato i filtri in questo ciclo.</td></tr>"]

options_comuni = "".join(f"<option>{html.escape(c)}</option>" for c in municipalities)
options_fonti = "".join(f"<option>{html.escape(c)}</option>" for c in portal_names)

DASH.write_text(f"""<!doctype html>
<html lang='it'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>F1 Seller Radar</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#0c0f0d;color:#eee;margin:0;padding:22px}}
.wrap{{max-width:1600px;margin:auto}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}}
.card{{background:#151a17;border:1px solid #2c3630;padding:14px 18px;border-radius:12px}}
.controls{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}}
select,input{{background:#151a17;color:#eee;border:1px solid #38443c;border-radius:9px;padding:10px}}
.tablewrap{{overflow:auto;border-radius:12px}}
table{{width:100%;border-collapse:collapse;background:#141815;min-width:1200px}}
th,td{{padding:9px;border-bottom:1px solid #2c332f;text-align:left;font-size:13px;vertical-align:top}}
th{{background:#1c221e;position:sticky;top:0}}
a{{color:#78e08f;font-weight:700}}
.score{{padding:5px 7px;border-radius:8px;font-weight:800}}
.high{{background:#5f2020}} .med{{background:#5d4b17}} .low{{background:#25442f}}
.note{{border-left:4px solid #78e08f;padding:12px;background:#171b18}}
.small{{font-size:12px;color:#abb5ae}}
</style>
</head>
<body><div class='wrap'>
<h1>F1 SELLER RADAR — v4</h1>
<div class='small'>Aggiornato: {datetime.now().strftime("%d/%m/%Y %H:%M")} · Controlli programmati 08:30 e 18:30 ora italiana.</div>
<div class='note'>Radar di fonti pubbliche. Gli indizi “privato/no agenzie” e i prezzi vanno sempre verificati aprendo la fonte. Nessun telefono, email o nominativo viene raccolto automaticamente.</div>
<div class='cards'>
<div class='card'>Opportunità: <b>{len(queue)}</b></div>
<div class='card'>Priorità alta: <b>{high}</b></div>
<div class='card'>Indizi privato: <b>{priv}</b></div>
<div class='card'>Fonti configurate: <b>{len(portals)}</b></div>
<div class='card'>Territori: <b>{len(municipalities)}</b></div>
<div class='card'>Query OK: <b>{ok_count}/{len(status_rows)}</b></div>
<div class='card'>Accettati nel ciclo: <b>{accepted_total}</b></div>
</div>
<div class='controls'>
<select id='comune'><option value=''>Tutti i territori</option>{options_comuni}</select>
<select id='fonte'><option value=''>Tutte le fonti</option>{options_fonti}</select>
<input id='testo' placeholder='Cerca indirizzo, titolo, segnale...'>
</div>
<div class='tablewrap'>
<table id='radar'><thead><tr>
<th>Score</th><th>Priorità</th><th>Comune</th><th>Fonte</th><th>Inserzionista</th>
<th>Immobile</th><th>Prezzo</th><th>Ribassi</th><th>Perché</th><th>Azione</th>
</tr></thead><tbody>{''.join(trs)}</tbody></table>
</div>
</div>
<script>
const comune=document.getElementById('comune'), fonte=document.getElementById('fonte'), testo=document.getElementById('testo');
function filtra(){{
  const c=comune.value.toLowerCase(), f=fonte.value.toLowerCase(), q=testo.value.toLowerCase();
  document.querySelectorAll('#radar tbody tr').forEach(tr=>{{
    const okC=!c || (tr.dataset.comune||'').toLowerCase()===c;
    const okF=!f || (tr.dataset.fonte||'').toLowerCase()===f;
    const okQ=!q || tr.innerText.toLowerCase().includes(q);
    tr.style.display=(okC&&okF&&okQ)?'':'none';
  }});
}}
comune.addEventListener('change',filtra); fonte.addEventListener('change',filtra); testo.addEventListener('input',filtra);
</script>
</body></html>""", encoding="utf-8")

print(f"F1 Seller Radar v4: {len(queue)} opportunita, {accepted_total} accettati, {ok_count}/{len(status_rows)} query OK.")
