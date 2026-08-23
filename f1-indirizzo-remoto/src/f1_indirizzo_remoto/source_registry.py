from urllib.parse import urlparse

from .schemas import SOURCE_STATES


def validate_source(url: str, state: str, title: str = "") -> dict:
    url = (url or "").strip()
    if state not in SOURCE_STATES:
        raise ValueError("Stato fonte non valido")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL fonte non valido")
    return {"url": url, "state": state, "title": (title or "").strip()[:300], "domain": parsed.netloc.lower()}
