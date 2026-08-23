from f1_indirizzo_remoto.query_builder import ISPEZIONE_URL, VISURA_URL, build_queries
from f1_indirizzo_remoto.schemas import PRACTICE_STATES
from f1_indirizzo_remoto.source_registry import validate_source


def test_minimum_queries_include_official_and_public_sources(normalized_address):
    queries = build_queries(normalized_address)
    urls = [item["url"] for item in queries]
    texts = [item["query"] for item in queries]
    assert VISURA_URL in urls
    assert ISPEZIONE_URL in urls
    assert any("paginebianche.it" in text for text in texts)
    assert any("telefono" in text for text in texts)
    assert len(queries) >= 13


def test_name_query_only_when_confirmed(normalized_address):
    assert not any(item["fonte"] == "Nominativo confermato" for item in build_queries(normalized_address))
    assert any(item["fonte"] == "Nominativo confermato" for item in build_queries(normalized_address, "Persona Inventata"))


def test_unavailable_source_and_captcha_wait_state_are_supported():
    result = validate_source("https://example.test/non-disponibile", "NON DISPONIBILE")
    assert result["state"] == "NON DISPONIBILE"
    assert "ATTESA OPERATORE" in PRACTICE_STATES
