from pathlib import Path


ALLOWED_UPLOADS = {".pdf", ".jpg", ".jpeg", ".png"}
REQUIRED_CONTACT_FIELDS = (
    "value",
    "subject_name",
    "source_url",
    "source_name",
    "acquired_at",
    "match_reason",
    "use_condition",
)


def validate_upload(filename: str, size: int, max_bytes: int) -> str:
    name = Path(filename or "").name
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_UPLOADS:
        raise ValueError("Formato non consentito: usare PDF, JPG o PNG")
    if size <= 0 or size > max_bytes:
        raise ValueError("Dimensione file non consentita")
    return suffix


def contact_blockers(contact: dict, practice: dict) -> list[str]:
    blockers = []
    if practice.get("privacy_status") == "NON CONTATTARE" or practice.get("status") == "NON CONTATTARE":
        blockers.append("Pratica marcata NON CONTATTARE")
    for field in REQUIRED_CONTACT_FIELDS:
        if not str(contact.get(field) or "").strip():
            blockers.append(f"Manca {field}")
    if not contact.get("operator_confirmed"):
        blockers.append("Manca conferma operatore")
    if contact.get("reliability") in {"C - DEBOLE", "X - SCARTATO", ""}:
        blockers.append("Attendibilita insufficiente")
    if contact.get("contact_status") == "NON CONTATTARE":
        blockers.append("Contatto marcato NON CONTATTARE")
    return blockers


def action_allowed(contact: dict, practice: dict) -> tuple[bool, list[str]]:
    blockers = contact_blockers(contact, practice)
    return not blockers, blockers


def safe_join(root: Path, candidate: Path) -> Path:
    root = root.resolve()
    candidate = candidate.resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError("Percorso non consentito")
    return candidate
