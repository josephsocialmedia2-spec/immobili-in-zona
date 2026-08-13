from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"
STATE_PATH = BASE / "state.json"
REPORT_CSV = BASE / "report.csv"
REPORT_HTML = BASE / "report.html"


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9à-ÿ]+", "-", value, flags=re.I)
    return value.strip("-")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def robots_allows(url: str, user_agent: str, timeout: int) -> bool:
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        req = urllib.request.Request(robots_url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="ignore")
        rp.parse(body.splitlines())
        return rp.can_fetch(user_agent, url)
    except Exception:
        return False


def fetch_text(url: str, user_agent: str, timeout: int) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        content_type = r.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return ""
        return r.read(2_000_000).decode("utf-8", errors="ignore")


def extract_links(html: str, base_url: str, markers: list[str], limit: int) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    out, seen = [], set()
    for href in hrefs:
        absolute = urllib.parse.urljoin(base_url, href)
        clean, _frag = urllib.parse.urldefrag(absolute)
        if not any(marker in clean for marker in markers):
            continue
        if clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def score_record(first_seen: str, seen_count: int, is_new: bool) -> tuple[int, str]:
    now = datetime.now(timezone.utc)
    try:
        first = datetime.fromisoformat(first_seen)
        days = max(0, (now - first).days)
    except Exception:
        days = 0
    score = 35
    reasons = []
    if is_new:
        score += 15
        reasons.append("nuova rilevazione")
    if days >= 30:
        score += 15
        reasons.append("30+ giorni monitorati")
    if days >= 60:
        score += 15
        reasons.append("60+ giorni monitorati")
    if seen_count >= 8:
        score += 10
        reasons.append("presenza ricorrente")
    return min(score, 100), ", ".join(reasons) or "monitoraggio attivo"


def write_reports(rows: list[dict]) -> None:
    fields = [
        "score", "comune", "fonte", "url", "prima_rilevazione",
        "ultima_rilevazione", "rilevazioni", "stato", "motivo"
    ]
    with REPORT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})

    body = []
    for r in rows:
        body.append(
            "<tr>"
            f"<td><b>{r['score']}</b></td><td>{r['comune']}</td><td>{r['fonte']}</td>"
            f"<td>{r['stato']}</td><td>{r['motivo']}</td>"
            f"<td><a href=\"{r['url']}\" target=\"_blank\" rel=\"noopener\">APRI FONTE</a></td>"
            "</tr>"
        )
    html = f"""<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>F1 Seller Radar</title><style>body{{font-family:Arial,sans-serif;margin:24px;background:#111;color:#eee}}table{{border-collapse:collapse;width:100%;background:#1b1b1b}}th,td{{padding:10px;border:1px solid #333;text-align:left}}th{{background:#252525}}a{{color:#6ee7a8}}.note{{color:#bbb}}</style></head><body>
<h1>F1 Seller Radar</h1><p class='note'>Solo URL e segnali pubblici. Nessuna estrazione automatica di telefoni/email. Contatto e verifica restano manuali.</p>
<table><thead><tr><th>Score</th><th>Comune</th><th>Fonte</th><th>Stato</th><th>Motivo</th><th>Azione</th></tr></thead><tbody>{''.join(body)}</tbody></table></body></html>"""
    REPORT_HTML.write_text(html, encoding="utf-8")


def main() -> None:
    cfg = load_json(CONFIG_PATH, {})
    state = load_json(STATE_PATH, {"items": {}})
    items = state.setdefault("items", {})
    ua = cfg.get("user_agent", "F1SellerRadar/1.0")
    timeout = int(cfg.get("timeout_seconds", 20))
    delay = float(cfg.get("request_delay_seconds", 4))
    limit = int(cfg.get("max_links_per_source_page", 80))
    now = datetime.now(timezone.utc).isoformat()

    for comune in cfg.get("municipalities", []):
        slug = slugify(comune)
        for source in cfg.get("sources", []):
            for template in source.get("url_templates", []):
                url = template.format(slug=slug)
                if not robots_allows(url, ua, timeout):
                    print(f"SKIP robots/indisponibile: {source.get('name')} {comune}")
                    continue
                try:
                    html = fetch_text(url, ua, timeout)
                    links = extract_links(html, url, source.get("listing_markers", []), limit)
                except Exception as exc:
                    print(f"ERRORE {source.get('name')} {comune}: {exc}")
                    time.sleep(delay)
                    continue

                for link in links:
                    key = hashlib.sha256(link.encode("utf-8")).hexdigest()[:24]
                    rec = items.get(key)
                    is_new = rec is None
                    if is_new:
                        rec = {
                            "url": link,
                            "comune": comune,
                            "fonte": source.get("name", "web"),
                            "prima_rilevazione": now,
                            "ultima_rilevazione": now,
                            "rilevazioni": 1,
                        }
                        items[key] = rec
                    else:
                        rec["ultima_rilevazione"] = now
                        rec["rilevazioni"] = int(rec.get("rilevazioni", 0)) + 1

                    score, reason = score_record(
                        rec["prima_rilevazione"], int(rec.get("rilevazioni", 1)), is_new
                    )
                    rec["score"] = score
                    rec["motivo"] = reason
                    rec["stato"] = "NUOVO" if is_new else "MONITORATO"
                time.sleep(delay)

    rows = sorted(items.values(), key=lambda r: (-int(r.get("score", 0)), r.get("comune", "")))
    save_json(STATE_PATH, state)
    write_reports(rows)
    print(f"OK: {len(rows)} opportunità monitorate")


if __name__ == "__main__":
    main()
