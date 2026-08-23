import csv
import json
import zipfile
from xml.etree import ElementTree

from pypdf import PdfReader

from f1_indirizzo_remoto.crm_export import HEADERS, export_csv, export_json, export_pdf, export_xlsx


def test_crm_csv_and_excel_have_separate_phones_and_clickable_link(db, practice_id, tmp_path):
    db.add_source(practice_id, {"source_name": "Fonte Demo", "url": "https://example.test/fonte", "state": "CONFERMATO"})
    base = {
        "subject_name": "Attivita Demo", "source_address": "Via Inventata 12A", "source_url": "https://example.test/fonte",
        "source_name": "Fonte Demo", "acquired_at": "2026-08-23T12:00", "context_text": "Demo", "match_reason": "Corrispondenza",
        "address_match": "CORRISPONDE", "reliability": "A - VERIFICATO", "use_condition": "Uso documentato",
        "operator_confirmed": True, "contact_status": "DA VERIFICARE", "last_outcome": "",
    }
    db.add_contact(practice_id, {**base, "contact_type": "FISSO", "value": "0111234567"})
    db.add_contact(practice_id, {**base, "contact_type": "MOBILE", "value": "3331234567"})
    rows = db.all_for_export()
    csv_path = export_csv(rows, tmp_path / "crm.csv")
    xlsx_path = export_xlsx(rows, tmp_path / "crm.xlsx")
    pdf_path = export_pdf(rows, tmp_path / "crm.pdf")
    json_path = export_json(rows, tmp_path / "crm.json")
    with csv_path.open(encoding="utf-8-sig") as handle:
        values = list(csv.DictReader(handle))[0]
    assert values["TELEFONO FISSO"] == "0111234567"
    assert values["TELEFONO MOBILE"] == "3331234567"
    with zipfile.ZipFile(xlsx_path) as archive:
        for name in archive.namelist():
            if name.endswith((".xml", ".rels")):
                ElementTree.fromstring(archive.read(name))
        rels = archive.read("xl/worksheets/_rels/sheet1.xml.rels").decode()
    assert "https://example.test/fonte" in rels
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
    assert practice_id in pdf_text
    assert "0111234567" in pdf_text
    assert "3331234567" in pdf_text
    assert len(HEADERS) == 42
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["records"][0]["ID PRATICA"] == practice_id
    assert "documents" not in payload["records"][0]
