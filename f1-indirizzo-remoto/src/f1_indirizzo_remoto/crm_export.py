import csv
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .letter_generator import _register_fonts


HEADERS = [
    "ID PRATICA", "DATA APERTURA", "FUNZIONARIO", "COMUNE", "CAP", "VIA", "CIVICO",
    "SCALA", "PIANO", "INTERNO", "INDIRIZZO ORIGINALE", "INDIRIZZO NORMALIZZATO", "LINK MAPPA",
    "STATO INDIRIZZO", "FOGLIO", "PARTICELLA", "SUBALTERNO", "CATEGORIA",
    "INTESTATARIO CATASTALE", "TITOLARE VERIFICATO", "TIPO E DATA DOCUMENTO", "TELEFONO FISSO", "TELEFONO MOBILE",
    "EMAIL/PEC", "LINK FONTE", "FONTE", "DATA ACQUISIZIONE CONTATTO", "LIVELLO ATTENDIBILITA", "CONDIZIONE D'USO",
    "STATO CONTATTO", "ULTIMO ESITO", "PROSSIMA AZIONE", "DATA PROSSIMA AZIONE",
    "LETTERA GENERATA", "DATA SPEDIZIONE", "RISPOSTA", "MOTIVAZIONE/TEMPI", "IMMOBILE/TIPOLOGIA", "NOTE",
    "PRIVACY/OPPOSIZIONE", "ULTIMA MODIFICA", "ID CANONICO CONDIVISO",
]


def _best_contacts(practice: dict) -> dict:
    result = {"FISSO": "", "MOBILE": "", "EMAIL": "", "PEC": "", "reliability": "", "use_condition": "", "contact_status": "", "acquired_at": ""}
    for contact in practice.get("contacts", []):
        kind = contact["contact_type"]
        if kind in result and not result[kind]:
            result[kind] = contact["value"]
        if not result["reliability"]:
            result["reliability"] = contact.get("reliability", "")
            result["use_condition"] = contact.get("use_condition", "")
            result["contact_status"] = contact.get("contact_status", "")
            result["acquired_at"] = contact.get("acquired_at", "")
    return result


def export_rows(practices: list[dict]) -> list[list]:
    rows = []
    for p in practices:
        c = _best_contacts(p)
        document = p.get("latest_document") or {}
        document_summary = " · ".join(value for value in (document.get("document_type", ""), document.get("acquired_at", "")) if value)
        rows.append([
            p["id"], p["opened_at"], p["operator"], p["comune"], p["cap"], p["via"], p["civico"],
            p["scala"], p["piano"], p["interno"], p["original_address"], p["normalized_address"], p["map_url"],
            p["address_status"], p["sheet"], p["parcel"], p["subaltern"], p["category"],
            p["cadastral_holder"], p["verified_owner"], document_summary, c["FISSO"], c["MOBILE"], c["EMAIL"] or c["PEC"],
            p.get("confirmed_source_url", ""), p.get("confirmed_source_name", ""), c["acquired_at"], c["reliability"],
            c["use_condition"], c["contact_status"], p["last_outcome"], p["next_action"], p["next_action_date"],
            "SI" if p["letter_generated"] else "NO", p["letter_sent_at"], p["response"], p["reason"], p["property_type"],
            p["notes"], p["privacy_status"], p["updated_at"], p["canonical_external_id"] or p["id"],
        ])
    return rows


def export_csv(practices: list[dict], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADERS)
        writer.writerows(export_rows(practices))
    return destination


def export_json(practices: list[dict], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    records = [dict(zip(HEADERS, values)) for values in export_rows(practices)]
    destination.write_text(json.dumps({"schema": "f1-indirizzo-remoto/v1", "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def _col_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _xml(value) -> str:
    return escape(str(value or ""), {'"': "&quot;"})


def export_xlsx(practices: list[dict], destination: Path) -> Path:
    rows = [HEADERS] + export_rows(practices)
    widths = [28, 22, 18, 18, 9, 24, 10, 9, 9, 9, 35, 42, 48, 22, 10, 12, 12, 12, 28, 28, 28, 18, 18, 25, 48, 20, 22, 20, 30, 20, 28, 26, 20, 16, 20, 25, 28, 25, 38, 22, 22, 30]
    sheet_rows, links = [], []
    for row_index, values in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(values, start=1):
            ref = f"{_col_name(column_index)}{row_index}"
            header = HEADERS[column_index - 1]
            is_link = header in {"LINK MAPPA", "LINK FONTE"} and bool(value)
            style = 1 if row_index == 1 else (2 if is_link else 0)
            cells.append(f'<c r="{ref}" t="inlineStr" s="{style}"><is><t>{_xml(value)}</t></is></c>')
            if row_index > 1 and is_link:
                links.append((ref, str(value)))
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    columns = "".join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths, 1))
    hyperlinks = "<hyperlinks>" + "".join(f'<hyperlink ref="{ref}" r:id="rId{i}"/>' for i, (ref, _) in enumerate(links, 1)) + "</hyperlinks>" if links else ""
    last_column = _col_name(len(HEADERS))
    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane xSplit="3" ySplit="1" topLeftCell="D2" activePane="bottomRight" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="18"/><cols>{columns}</cols><sheetData>{"".join(sheet_rows)}</sheetData><autoFilter ref="A1:{last_column}{max(1, len(rows))}"/>{hyperlinks}</worksheet>'''
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="{_xml(url)}" TargetMode="External"/>' for i, (_, url) in enumerate(links, 1)) + '</Relationships>'
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>',
        "docProps/core.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>CRM F1 Indirizzo Remoto</dc:title><dc:creator>F1 Immobiliare</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{datetime.now(timezone.utc).isoformat()}</dcterms:created></cp:coreProperties>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="CRM OPERATIVO" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="3"><font><sz val="10"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Aptos"/></font><font><u/><color rgb="FF0563C1"/><sz val="10"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF174F2A"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
        "xl/worksheets/sheet1.xml": sheet,
    }
    if links:
        files["xl/worksheets/_rels/sheet1.xml.rels"] = rels
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return destination


def _pdf_text(value) -> str:
    return escape(str(value or "—"))


def _pdf_attr(value) -> str:
    return escape(str(value or ""), {'"': "&quot;", "'": "&#39;"})


def export_pdf(practices: list[dict], destination: Path) -> Path:
    """Create a printable CRM dossier; Excel remains the full-width operational view."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    regular_font, bold_font = _register_fonts()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("CRMTitle", parent=styles["Title"], fontName=bold_font, fontSize=20, leading=24, textColor=colors.HexColor("#174F2A"))
    heading = ParagraphStyle("CRMHeading", parent=styles["Heading2"], fontName=bold_font, fontSize=13, leading=17, textColor=colors.HexColor("#174F2A"), spaceAfter=7)
    body = ParagraphStyle("CRMBody", parent=styles["BodyText"], fontName=regular_font, fontSize=8.5, leading=11)
    label = ParagraphStyle("CRMLabel", parent=body, fontName=bold_font, textColor=colors.HexColor("#536158"))
    doc = SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title="CRM F1 Indirizzo Remoto", author="F1 Immobiliare")
    story = [
        Paragraph("CRM F1 INDIRIZZO REMOTO", title),
        Paragraph(f"Esportazione del {datetime.now().strftime('%d/%m/%Y %H:%M')} · {len(practices)} pratiche", body),
        Spacer(1, 7 * mm),
    ]
    for index, practice in enumerate(practices):
        contacts = _best_contacts(practice)
        document = practice.get("latest_document") or {}
        source_url = practice.get("confirmed_source_url", "")
        source_value = f'<link href="{_pdf_attr(source_url)}" color="#0563C1">{_pdf_text(source_url)}</link>' if source_url.startswith(("http://", "https://")) else "—"
        map_url = practice.get("map_url", "")
        map_value = f'<link href="{_pdf_attr(map_url)}" color="#0563C1">APRI MAPPA</link>' if map_url.startswith(("http://", "https://")) else "—"
        story.extend([
            Paragraph(f"{_pdf_text(practice['id'])} · {_pdf_text(practice['status'])}", heading),
            Table([
                [Paragraph("INDIRIZZO", label), Paragraph(_pdf_text(practice["normalized_address"]), body)],
                [Paragraph("MAPPA", label), Paragraph(map_value, body)],
                [Paragraph("TITOLARITÀ", label), Paragraph(f"Catastale: {_pdf_text(practice['cadastral_holder'])}<br/>Verificato: {_pdf_text(practice['verified_owner'])}", body)],
                [Paragraph("DATI CATASTALI", label), Paragraph(f"Foglio {_pdf_text(practice['sheet'])} · Particella {_pdf_text(practice['parcel'])} · Sub {_pdf_text(practice['subaltern'])} · Categoria {_pdf_text(practice['category'])}", body)],
                [Paragraph("DOCUMENTO", label), Paragraph(f"{_pdf_text(document.get('document_type'))} · {_pdf_text(document.get('acquired_at'))}", body)],
                [Paragraph("CONTATTI", label), Paragraph(f"Fisso: {_pdf_text(contacts['FISSO'])}<br/>Mobile: {_pdf_text(contacts['MOBILE'])}<br/>Email/PEC: {_pdf_text(contacts['EMAIL'] or contacts['PEC'])}", body)],
                [Paragraph("FONTE", label), Paragraph(source_value, body)],
                [Paragraph("AZIONE", label), Paragraph(f"Ultimo esito: {_pdf_text(practice['last_outcome'])}<br/>Prossima: {_pdf_text(practice['next_action'])} · {_pdf_text(practice['next_action_date'])}", body)],
                [Paragraph("PRIVACY", label), Paragraph(_pdf_text(practice["privacy_status"]), body)],
                [Paragraph("NOTE", label), Paragraph(_pdf_text(practice["notes"]), body)],
            ], colWidths=[34 * mm, 146 * mm], style=TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F5F2")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C8D0CA")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])),
        ])
        if index < len(practices) - 1:
            story.append(PageBreak())
    if not practices:
        story.append(Paragraph("Nessuna pratica presente.", body))
    doc.build(story)
    return destination
