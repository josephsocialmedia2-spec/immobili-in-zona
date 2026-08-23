import hashlib
import re
from pathlib import Path

from pypdf import PdfReader


FIELD_PATTERNS = {
    "sheet": (r"\bfoglio\s*[:n.]*\s*([A-Z0-9/-]+)",),
    "parcel": (r"\b(?:particella|mappale)\s*[:n.]*\s*([A-Z0-9/-]+)",),
    "subaltern": (r"\b(?:subalterno|sub\.)\s*[:n.]*\s*([A-Z0-9/-]+)",),
    "category": (r"\bcategoria\s*[:]*\s*([A-Z]/?\d+)",),
    "class": (r"\bclasse\s*[:]*\s*([A-Z0-9]+)",),
    "consistency": (r"\bconsistenza\s*[:]*\s*([^\n;]{1,50})",),
    "cadastral_area": (r"\bsuperficie\s*(?:catastale)?\s*[:]*\s*([^\n;]{1,50})",),
    "cadastral_income": (r"\brendita\s*(?:catastale)?\s*[:€]*\s*([0-9.,]+)",),
    "holder_share": (r"\b(?:quota|diritto)\s*[:]*\s*([^\n;]{1,80})",),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def extract_image_ocr(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image

        return pytesseract.image_to_string(Image.open(path), lang="ita").strip()
    except (ImportError, RuntimeError, OSError):
        return ""


def propose_fields(text: str) -> dict:
    proposed = {}
    for field, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text or "", re.I)
            if match:
                proposed[field] = match.group(1).strip()
                break
    holders = re.findall(r"(?:intestat(?:ario|aria|ari|arie|o|a)|titolare)\s*[:\-]\s*([^\n;]{3,100})", text or "", re.I)
    if holders:
        proposed["cadastral_holder_proposed"] = " ; ".join(dict.fromkeys(value.strip() for value in holders[:10]))
    return proposed


def parse_document(path: Path) -> dict:
    suffix = path.suffix.lower()
    text = extract_pdf(path) if suffix == ".pdf" else extract_image_ocr(path)
    return {
        "sha256": sha256_file(path),
        "extracted_text": text,
        "proposed_fields": propose_fields(text),
        "needs_ocr": suffix != ".pdf" and not text,
        "has_text": bool(text.strip()),
    }
