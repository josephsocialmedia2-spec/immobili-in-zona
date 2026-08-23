from pathlib import Path

import pytest

from f1_indirizzo_remoto.config import Settings
from f1_indirizzo_remoto.database import Database


@pytest.fixture
def settings(tmp_path):
    value = Settings(tmp_path, "127.0.0.1", 8765, "test-secret", 2 * 1024 * 1024, "https://f1immobiliare.com")
    value.ensure_directories()
    return value


@pytest.fixture
def db(settings):
    database = Database(settings.database_path, settings.backups_dir)
    database.initialize()
    return database


@pytest.fixture
def normalized_address():
    return {
        "comune": "Comune Esempio", "provincia": "TO", "via": "Via Inventata", "civico": "12A",
        "cap": "10000", "scala": "", "piano": "", "interno": "", "frazione": "",
        "nome_immobile": "Unita dimostrativa", "fonte_iniziale": "Fonte sintetica",
        "link_iniziale": "https://example.test/annuncio", "nota": "Dati inventati", "funzionario": "Operatore Test",
        "motivo": "Test automatico", "indirizzo_originale": "Comune Esempio | TO | Via Inventata | 12A",
        "indirizzo_normalizzato": "Via Inventata 12A, Comune Esempio (TO)",
        "duplicate_key": "comune esempio|via inventata|12a", "map_url": "https://www.google.com/maps/search/?api=1&query=test",
        "canonical_external_id": "RADAR-DEMO-001",
    }


@pytest.fixture
def practice_id(db, normalized_address):
    return db.create_practice(normalized_address)
