from pypdf import PdfReader

from f1_indirizzo_remoto.letter_generator import PRIMARY_PHONE, SECONDARY_PHONE, generate_letter


def test_letter_without_name_and_with_required_contacts(tmp_path, normalized_address):
    practice = {"id": "F1-IR-DEMO-0001", "normalized_address": normalized_address["indirizzo_normalizzato"]}
    target = generate_letter(practice, tmp_path / "lettera.pdf", "https://f1immobiliare.com")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(target)).pages)
    assert "proprietario dell'immobile" in text
    assert PRIMARY_PHONE in text
    assert SECONDARY_PHONE in text
    assert practice["id"] in text


def test_letter_uses_confirmed_name_when_explicitly_supplied(tmp_path, normalized_address):
    practice = {"id": "F1-IR-DEMO-0002", "normalized_address": normalized_address["indirizzo_normalizzato"]}
    target = generate_letter(practice, tmp_path / "lettera_nome.pdf", "https://f1immobiliare.com", "Persona Inventata")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(target)).pages)
    assert "Persona Inventata" in text
