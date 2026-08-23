import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BRIDGE = Path(__file__).parents[2] / "seller_radar_auto" / "f1_remote_bridge.py"
SPEC = importlib.util.spec_from_file_location("f1_remote_bridge", BRIDGE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_bridge_builds_local_prefill_only_with_exact_civic():
    url = MODULE.build_import_url({
        "COMUNE": "Comune Esempio", "DOVE_ANDRE": "Via Inventata, 12/A",
        "URL": "https://example.test/annuncio/1", "TITOLO": "Casa in Via Inventata 12/A", "FONTE": "Fonte demo",
        "CONTATTI_PUBBLICI": "PHONE:0111234567", "FONTE_CONTATTO": "https://example.test/contatto",
    })
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "127.0.0.1:8765"
    assert query["via"] == ["Via Inventata"]
    assert query["civico"] == ["12/A"]
    assert query["canonical_id"][0].startswith("RADAR-")
    assert query["telefono"] == ["0111234567"]
    assert query["telefono_fonte"] == ["https://example.test/contatto"]


def test_bridge_blocks_unknown_civic():
    assert MODULE.build_import_url({"COMUNE": "Esempio", "DOVE_ANDRE": "Via Inventata — CIVICO DA VERIFICARE"}) == ""


def test_bridge_blocks_address_not_supported_by_listing_title():
    row = {
        "COMUNE": "Comune Esempio", "DOVE_ANDRE": "Via Agenzia 10",
        "TITOLO": "Tutti gli immobili in vendita", "URL": "https://example.test/elenco",
    }
    assert MODULE.build_import_url(row) == ""
