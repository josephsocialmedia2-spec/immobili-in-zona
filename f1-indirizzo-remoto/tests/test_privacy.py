import pytest

from f1_indirizzo_remoto.audit_log import redact_for_diagnostic
from f1_indirizzo_remoto.privacy_guard import action_allowed, safe_join, validate_upload


def complete_contact():
    return {
        "value": "0111234567", "subject_name": "Attivita Demo", "source_url": "https://example.test",
        "source_name": "Fonte Demo", "acquired_at": "2026-08-23T12:00", "match_reason": "Corrispondenza esatta",
        "use_condition": "Contatto manuale documentato", "operator_confirmed": True,
        "reliability": "A - VERIFICATO", "contact_status": "DA VERIFICARE",
    }


def test_complete_verified_contact_is_allowed():
    allowed, blockers = action_allowed(complete_contact(), {"privacy_status": "ATTIVO", "status": "CONTATTO UTILIZZABILE"})
    assert allowed and not blockers


def test_missing_source_blocks_action():
    contact = complete_contact(); contact["source_url"] = ""
    allowed, blockers = action_allowed(contact, {"privacy_status": "ATTIVO"})
    assert not allowed and any("source_url" in item for item in blockers)


def test_non_contact_prevalence():
    allowed, blockers = action_allowed(complete_contact(), {"privacy_status": "NON CONTATTARE"})
    assert not allowed and any("NON CONTATTARE" in item for item in blockers)


def test_upload_type_and_size():
    assert validate_upload("visura.pdf", 1000, 2000) == ".pdf"
    for name, size in (("segreto.exe", 100), ("foto.jpg", 3000)):
        try:
            validate_upload(name, size, 2000)
        except ValueError:
            pass
        else:
            raise AssertionError("Upload non sicuro accettato")


def test_path_traversal_is_blocked(tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path / "uploads", tmp_path / "outside.pdf")


def test_diagnostics_redact_credentials_and_sensitive_values():
    assert redact_for_diagnostic("value", "dato sensibile") == "[DATO LOCALE OMESSO]"
    assert "dato sensibile" not in redact_for_diagnostic("verified_owner", "dato sensibile")
