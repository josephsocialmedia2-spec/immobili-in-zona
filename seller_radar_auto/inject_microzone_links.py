#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DASH = ROOT / "dashboard.html"
TAGS = [
    "<script src='microzone_link.js'></script>",
    "<script src='cadastral_overlay.js'></script>",
]

text = DASH.read_text(encoding="utf-8")
for tag in TAGS:
    if tag not in text:
        text = text.replace("</body></html>", tag + "</body></html>")
DASH.write_text(text, encoding="utf-8")

check = DASH.read_text(encoding="utf-8")
for tag in TAGS:
    if check.count(tag) != 1:
        raise SystemExit(f"FAIL DASHBOARD LINK: script tag non univoco: {tag}")
if check.count("class='seller-row'") != 660:
    raise SystemExit("FAIL DASHBOARD LINK: il MASTER non contiene più 660 righe")
print("PASS DASHBOARD LINK | MASTER 660 preservato + microzona + overlay NOVITA/Catasto")
