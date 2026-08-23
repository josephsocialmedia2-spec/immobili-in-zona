"""Costruisce collegamenti locali espliciti dal Seller Radar a F1 Indirizzo Remoto."""
from hashlib import sha256
import re
from urllib.parse import urlencode


CIVIC_RE = re.compile(r"^(?P<via>.+?)[,\s]+(?P<civico>\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|[A-Za-z])?)$", re.I)


def split_exact_address(address: str) -> tuple[str, str]:
    value = re.sub(r"\s+", " ", str(address or "")).strip(" ,")
    if not value or "DA VERIFICARE" in value.upper():
        return "", ""
    match = CIVIC_RE.match(value)
    if not match:
        return "", ""
    return match.group("via").strip(" ,"), re.sub(r"\s+", "", match.group("civico"))


def address_supported_by_listing(row: dict, via: str, civico: str) -> bool:
    """Avoid mistaking an agency/listing-page address for the advertised property."""
    if str(row.get("INDIRIZZO_CONFERMATO") or "").strip().upper() == "SI":
        return True
    title = re.sub(r"[^a-z0-9]+", " ", str(row.get("TITOLO") or row.get("COSA_CERCO") or "").lower()).strip()
    candidate = re.sub(r"[^a-z0-9]+", " ", f"{via} {civico}".lower()).strip()
    return bool(candidate and candidate in title)


def build_import_url(row: dict, base_url: str = "http://127.0.0.1:8765") -> str:
    via, civico = split_exact_address(row.get("DOVE_ANDRE", ""))
    comune = str(row.get("COMUNE") or "").strip()
    if not (comune and via and civico) or not address_supported_by_listing(row, via, civico):
        return ""
    source_url = str(row.get("URL") or "").strip()
    contact_source = str(row.get("FONTE_CONTATTO") or "").split(" | ")[0].strip()
    public_contact = str(row.get("CONTATTI_PUBBLICI") or "").split(" | ")[0].strip()
    public_phone = re.sub(r"^[A-Z_]+:", "", public_contact, flags=re.I).strip() if contact_source else ""
    canonical = "RADAR-" + sha256(source_url.encode("utf-8")).hexdigest()[:16].upper()
    query = urlencode({
        "canonical_id": canonical,
        "comune": comune,
        "provincia": str(row.get("PROVINCIA") or "TO").strip().upper(),
        "via": via,
        "civico": civico,
        "url": source_url,
        "titolo": str(row.get("TITOLO") or row.get("COSA_CERCO") or "")[:240],
        "segnale": str(row.get("MOTIVI") or row.get("SELLER_SIGNAL") or "")[:240],
        "fonte": str(row.get("FONTE") or "Radar F1")[:100],
        "telefono": public_phone[:40],
        "telefono_fonte": contact_source[:500],
    })
    return f"{base_url.rstrip('/')}/radar/importa?{query}"
