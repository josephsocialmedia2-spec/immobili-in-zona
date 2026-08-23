import re
import unicodedata
from dataclasses import asdict

from .schemas import AddressInput


ABBREVIATIONS = {
    "V.": "Via",
    "VIALE": "Viale",
    "P.ZZA": "Piazza",
    "PZA": "Piazza",
    "C.SO": "Corso",
    "CORSO": "Corso",
    "LOC.": "Localita",
    "FRAZ.": "Frazione",
}


def clean(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def title_preserving_numbers(value: str) -> str:
    return " ".join(part if any(ch.isdigit() for ch in part) else part.capitalize() for part in clean(value).split())


def normalize_street(value: str) -> str:
    value = clean(value)
    upper = value.upper()
    for short, full in ABBREVIATIONS.items():
        if upper == short or upper.startswith(short + " "):
            value = full + value[len(short):]
            break
    return title_preserving_numbers(value)


def normalize_civic(value: str) -> str:
    value = clean(value).upper().replace(" ", "")
    if not re.fullmatch(r"\d+[A-Z]?(?:[/.-][A-Z0-9]+)?", value):
        raise ValueError("Numero civico non valido o ambiguo")
    return value


def normalize_address(data: AddressInput) -> dict:
    original = asdict(data)
    if not clean(data.comune) or not clean(data.provincia) or not clean(data.via) or not clean(data.civico):
        raise ValueError("Comune, provincia, via e numero civico sono obbligatori")
    normalized = {
        "comune": title_preserving_numbers(data.comune),
        "provincia": clean(data.provincia).upper()[:2],
        "via": normalize_street(data.via),
        "civico": normalize_civic(data.civico),
        "cap": re.sub(r"\D", "", data.cap or "")[:5],
        "scala": clean(data.scala).upper(),
        "piano": clean(data.piano).upper(),
        "interno": clean(data.interno).upper(),
        "frazione": title_preserving_numbers(data.frazione),
        "nome_immobile": clean(data.nome_immobile),
        "fonte_iniziale": clean(data.fonte_iniziale),
        "link_iniziale": clean(data.link_iniziale),
        "nota": clean(data.nota),
        "funzionario": clean(data.funzionario),
        "motivo": clean(data.motivo),
    }
    normalized["indirizzo_originale"] = " | ".join(
        str(original[key]) for key in ("comune", "provincia", "via", "civico")
    )
    normalized["indirizzo_normalizzato"] = f"{normalized['via']} {normalized['civico']}, {normalized['comune']} ({normalized['provincia']})"
    normalized["duplicate_key"] = "|".join(
        (normalized["comune"].casefold(), normalized["via"].casefold(), normalized["civico"].casefold())
    )
    return normalized
