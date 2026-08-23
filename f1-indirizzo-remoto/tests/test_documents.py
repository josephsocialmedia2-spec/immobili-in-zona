from reportlab.pdfgen import canvas

from f1_indirizzo_remoto.document_parser import parse_document, propose_fields


def test_native_pdf_proposes_fields(tmp_path):
    pdf = tmp_path / "visura_demo.pdf"
    writer = canvas.Canvas(str(pdf))
    writer.drawString(50, 780, "Documento dimostrativo - Foglio 10 Particella 20 Subalterno 3 Categoria A/2")
    writer.save()
    result = parse_document(pdf)
    assert result["has_text"]
    assert result["proposed_fields"]["sheet"] == "10"
    assert result["proposed_fields"]["parcel"] == "20"
    assert result["proposed_fields"]["subaltern"] == "3"


def test_empty_scanned_image_stays_unverified(tmp_path):
    image = tmp_path / "scan.png"
    image.write_bytes(b"not-a-real-image")
    result = parse_document(image)
    assert not result["has_text"]
    assert result["needs_ocr"]


def test_visura_without_holder_does_not_invent_one():
    assert "cadastral_holder_proposed" not in propose_fields("Foglio 10 Particella 20")


def test_multiple_holders_remain_explicit_proposals():
    fields = propose_fields("Intestatario: Persona Inventata Uno\nTitolare: Persona Inventata Due")
    assert "Persona Inventata Uno" in fields["cadastral_holder_proposed"]
    assert "Persona Inventata Due" in fields["cadastral_holder_proposed"]
