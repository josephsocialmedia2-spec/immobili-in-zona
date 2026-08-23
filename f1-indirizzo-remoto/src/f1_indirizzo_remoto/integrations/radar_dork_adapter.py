from ..address_normalizer import normalize_address
from ..schemas import AddressInput


ALLOWED_FIELDS = {"canonical_id", "comune", "provincia", "via", "civico", "url", "titolo", "segnale", "telefono", "telefono_fonte", "fonte"}


def prepare_import(payload: dict) -> dict:
    clean = {key: str(value or "").strip() for key, value in payload.items() if key in ALLOWED_FIELDS}
    normalized = normalize_address(AddressInput(
        comune=clean.get("comune", ""),
        provincia=clean.get("provincia", "TO"),
        via=clean.get("via", ""),
        civico=clean.get("civico", ""),
        fonte_iniziale=clean.get("fonte", "Radar F1"),
        link_iniziale=clean.get("url", ""),
        nota=" | ".join(value for value in (clean.get("titolo", ""), clean.get("segnale", "")) if value),
        motivo="Import da radar annunci",
    ))
    normalized["canonical_external_id"] = clean.get("canonical_id", "")
    normalized["public_phone_from_radar"] = clean.get("telefono", "")
    normalized["public_phone_source_from_radar"] = clean.get("telefono_fonte", "")
    return normalized
