#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DASH = ROOT / "dashboard.html"
TAG = "<script src='microzone_link.js'></script>"

text = DASH.read_text(encoding="utf-8")
if TAG not in text:
    text = text.replace("</body></html>", TAG + "</body></html>")
    DASH.write_text(text, encoding="utf-8")

check = DASH.read_text(encoding="utf-8")
if check.count(TAG) != 1:
    raise SystemExit("FAIL MICROZONE LINK: script tag non univoco")
if check.count("class='seller-row'") != 660:
    raise SystemExit("FAIL MICROZONE LINK: il MASTER non contiene più 660 righe")
print("PASS MICROZONE LINK | dashboard 660 preservata + collegamento Pagina 1 -> Pagina 2")
