import pytest

from f1_indirizzo_remoto.integrations.radar_dork_adapter import prepare_import


def test_radar_adapter_whitelists_and_preserves_canonical_id():
    result = prepare_import({
        "canonical_id": "RADAR-DEMO-001", "comune": "Comune Esempio", "provincia": "TO",
        "via": "Via Inventata", "civico": "12", "url": "https://example.test/annuncio",
        "titolo": "Casa demo", "segnale": "Ribasso", "telefono": "0111234567",
        "telefono_fonte": "https://example.test/contatto", "password": "non-deve-passare",
    })
    assert result["canonical_external_id"] == "RADAR-DEMO-001"
    assert "password" not in result
    assert result["public_phone_from_radar"] == "0111234567"
    assert result["public_phone_source_from_radar"] == "https://example.test/contatto"


def test_radar_import_requires_civic():
    with pytest.raises(ValueError):
        prepare_import({"comune": "Esempio", "provincia": "TO", "via": "Via Inventata", "civico": ""})
