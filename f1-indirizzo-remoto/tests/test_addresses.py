import pytest

from f1_indirizzo_remoto.address_normalizer import normalize_address, normalize_civic
from f1_indirizzo_remoto.schemas import AddressInput


def test_complete_address_is_normalized():
    result = normalize_address(AddressInput("comune esempio", "to", "v. inventata", "12 a"))
    assert result["comune"] == "Comune Esempio"
    assert result["provincia"] == "TO"
    assert result["via"] == "Via Inventata"
    assert result["civico"] == "12A"


@pytest.mark.parametrize("field", ["comune", "provincia", "via", "civico"])
def test_required_address_fields(field):
    data = {"comune": "Esempio", "provincia": "TO", "via": "Via Inventata", "civico": "1"}
    data[field] = ""
    with pytest.raises(ValueError):
        normalize_address(AddressInput(**data))


def test_ambiguous_civic_is_rejected():
    with pytest.raises(ValueError):
        normalize_civic("senza numero")
