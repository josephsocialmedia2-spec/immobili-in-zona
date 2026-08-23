import pytest

from f1_indirizzo_remoto.contact_validator import classify_contact, validate_contact


@pytest.mark.parametrize(("value", "expected"), [("011 1234567", "FISSO"), ("333 1234567", "MOBILE"), ("demo@example.test", "EMAIL")])
def test_contact_classification(value, expected):
    assert classify_contact(value)[0] == expected


def test_unrecognized_contact_is_rejected():
    with pytest.raises(ValueError):
        classify_contact("numero inventato")


def test_other_street_is_kept_separate_and_weakened(normalized_address):
    result = validate_contact({
        "value": "0111234567", "contact_type": "FISSO", "subject_name": "Attivita Demo",
        "source_address": "Via Diversa 9, Comune Esempio", "source_url": "https://example.test/contatti",
        "source_name": "Fonte Demo", "acquired_at": "2026-08-23T12:00", "match_reason": "Risultato ricerca",
        "reliability": "A - VERIFICATO", "use_condition": "Verifica manuale", "operator_confirmed": True,
    }, normalized_address)
    assert result["address_match"] == "ALTRA VIA"
    assert result["reliability"] == "C - DEBOLE"


def test_contact_requires_source_url(normalized_address):
    with pytest.raises(ValueError):
        validate_contact({"value": "0111234567", "subject_name": "Demo", "source_url": ""}, normalized_address)
