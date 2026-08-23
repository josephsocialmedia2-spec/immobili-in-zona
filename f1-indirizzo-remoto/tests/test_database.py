import pytest

from f1_indirizzo_remoto.database import Database, DuplicatePracticeError


def test_practice_id_and_required_next_action(db, normalized_address):
    practice_id = db.create_practice(normalized_address)
    practice = db.get_practice(practice_id)
    assert practice_id.startswith("F1-IR-")
    assert practice["last_outcome"]
    assert practice["next_action"] == "VERIFICA INDIRIZZO"
    assert practice["next_action_date"]


def test_duplicate_is_not_merged(db, normalized_address):
    first = db.create_practice(normalized_address)
    with pytest.raises(DuplicatePracticeError) as error:
        db.create_practice(normalized_address)
    assert error.value.practice_id == first


def test_multiple_units_remain_separate(db, practice_id):
    one = db.add_unit(practice_id, {"sheet": "1", "parcel": "20", "subaltern": "1"})
    two = db.add_unit(practice_id, {"sheet": "1", "parcel": "20", "subaltern": "2"})
    practice = db.get_practice_full(practice_id)
    assert one != two
    assert {unit["subaltern"] for unit in practice["units"]} == {"1", "2"}


def test_duplicate_canonical_id_opens_existing_practice(db, normalized_address):
    first = db.create_practice(normalized_address)
    second_address = {**normalized_address, "civico": "99", "indirizzo_normalizzato": "Via Inventata 99, Comune Esempio (TO)", "duplicate_key": "comune esempio|via inventata|99"}
    with pytest.raises(DuplicatePracticeError) as error:
        db.create_practice(second_address)
    assert error.value.practice_id == first
    assert db.find_existing_practice(second_address["duplicate_key"], second_address["canonical_external_id"]) == first


def test_queries_are_parameterized_against_simple_injection(db):
    assert db.list_practices(query="%' OR 1=1 --") == []


def test_corrupt_database_restores_last_valid_backup(db, normalized_address):
    practice_id = db.create_practice(normalized_address)
    backup = db.backup()
    assert backup.is_file()
    db.path.write_bytes(b"database corrotta dimostrativa")
    restored = Database(db.path, db.backups_dir)
    restored.initialize()
    assert restored.get_practice(practice_id)["id"] == practice_id
    assert list(db.backups_dir.glob("database-danneggiato-*.sqlite3"))
