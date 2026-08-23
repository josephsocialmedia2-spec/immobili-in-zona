import re
from urllib.parse import urlparse

from .schemas import RELIABILITY_LEVELS


EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.I)


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("39") and len(digits) > 10:
        digits = digits[2:]
    return digits


def classify_contact(value: str, declared_type: str = "") -> tuple[str, str]:
    value = (value or "").strip()
    declared_type = (declared_type or "").strip().upper()
    if EMAIL_RE.fullmatch(value):
        return ("PEC" if declared_type == "PEC" else "EMAIL"), value.lower()
    phone = normalize_phone(value)
    if phone.startswith("0") and 8 <= len(phone) <= 11:
        return "FISSO", phone
    if phone.startswith("3") and 9 <= len(phone) <= 10:
        return ("WHATSAPP" if declared_type == "WHATSAPP" else "MOBILE"), phone
    if declared_type == "MODULO" and value.startswith(("http://", "https://")):
        return "MODULO", value
    raise ValueError("Recapito non riconosciuto")


def validate_contact(data: dict, practice: dict) -> dict:
    contact_type, normalized = classify_contact(data.get("value", ""), data.get("contact_type", ""))
    reliability = data.get("reliability", "C - DEBOLE")
    if reliability not in RELIABILITY_LEVELS:
        raise ValueError("Attendibilita non valida")
    source_url = (data.get("source_url") or "").strip()
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Ogni contatto richiede un URL fonte valido")
    source_address = (data.get("source_address") or "").strip()
    address_match = data.get("address_match", "DA VERIFICARE")
    if source_address and practice.get("via", "").casefold() not in source_address.casefold():
        address_match = "ALTRA VIA"
        if reliability != "X - SCARTATO":
            reliability = "C - DEBOLE"
    return {
        "contact_type": contact_type,
        "value": normalized,
        "subject_name": (data.get("subject_name") or "").strip(),
        "source_address": source_address,
        "source_url": source_url,
        "source_name": (data.get("source_name") or parsed.netloc).strip(),
        "acquired_at": (data.get("acquired_at") or "").strip(),
        "context_text": (data.get("context_text") or "").strip()[:1000],
        "match_reason": (data.get("match_reason") or "").strip()[:500],
        "address_match": address_match,
        "reliability": reliability,
        "use_condition": (data.get("use_condition") or "").strip()[:500],
        "operator_confirmed": bool(data.get("operator_confirmed")),
        "contact_status": (data.get("contact_status") or "DA VERIFICARE").strip(),
        "last_outcome": (data.get("last_outcome") or "").strip()[:500],
    }
