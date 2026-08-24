#!/usr/bin/env python3
import csv
import json
import os
import re
import smtplib
import zipfile
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
QUEUE = DATA / "work_queue.csv"
SENT = DATA / "email_sent.json"

SMTP_HOST = os.getenv("F1_EMAIL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("F1_EMAIL_SMTP_PORT", "465"))
EMAIL_USER = os.getenv("F1_EMAIL_USER", "").strip()
EMAIL_PASS = os.getenv("F1_EMAIL_APP_PASSWORD", "").strip()
EMAIL_TO = (os.getenv("F1_EMAIL_TO") or "f1immobiliaresusa@outlook.it").strip()

HEADERS = [
    "PRIORITA", "SCORE", "COMUNE", "VIA / CIVICO", "IMMOBILE",
    "PREZZO ATTUALE", "PREZZO PRECEDENTE", "RIBASSI", "IN VENDITA DA GG",
    "SELLER SIGNAL", "AZIONE", "FONTE", "NOME INSERZIONISTA",
    "TELEFONI FISSI", "TELEFONI MOBILI", "EMAIL PUBBLICHE",
    "FONTE CONTATTO", "NUOVA", "LINK",
]


def row_id(row):
    return (row.get("URL") or "").strip()


def load_rows():
    if not QUEUE.exists():
        return []
    with QUEUE.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_sent():
    if not SENT.exists():
        return set()
    try:
        return set(json.loads(SENT.read_text(encoding="utf-8")).get("sent_ids", []))
    except Exception:
        return set()


def normalize_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("39") and len(digits) > 10:
        digits = digits[2:]
    return digits


def extract_contacts(row):
    raw = " | ".join([
        row.get("CONTATTI_PUBBLICI") or "",
        row.get("TELEFONO") or "",
        row.get("EMAIL") or "",
    ])
    emails = sorted(set(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", raw, re.I)))
    candidates = re.findall(r"(?<!\d)(?:\+39[ .-]?)?(?:0\d{1,3}|3\d{2})(?:[ .-]?\d){5,8}(?!\d)", raw)
    phones = sorted({normalize_phone(value) for value in candidates if 8 <= len(normalize_phone(value)) <= 11})
    fixed = [value for value in phones if value.startswith("0")]
    mobile = [value for value in phones if value.startswith("3")]
    return " ; ".join(fixed), " ; ".join(mobile), " ; ".join(emails)


def days_on_market(value):
    if not value:
        return ""
    try:
        first = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if first.tzinfo is None:
            first = first.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - first).days)
    except Exception:
        return ""


def number(value):
    if value in (None, ""):
        return ""
    try:
        return int(float(str(value).replace(".", "").replace(",", ".")))
    except Exception:
        return value


def report_rows(rows, sent):
    output = []
    for row in rows:
        fixed, mobile, emails = extract_contacts(row)
        output.append([
            row.get("PRIORITA") or "",
            number(row.get("SCORE")),
            row.get("COMUNE") or "",
            row.get("DOVE_ANDRE") or row.get("INDIRIZZO") or "CIVICO DA VERIFICARE",
            row.get("COSA_CERCO") or row.get("TITOLO") or "IMMOBILE DA VERIFICARE",
            number(row.get("PREZZO_OPERATIVO") or row.get("PREZZO")),
            number(row.get("PREZZO_PRECEDENTE")),
            number(row.get("RIBASSI")),
            days_on_market(row.get("PRIMA_RILEVAZIONE")),
            row.get("INDIZIO_INSERZIONISTA") or "",
            row.get("ISTRUZIONE_OPERATIVA") or "APRI FONTE E VERIFICA INDIRIZZO",
            row.get("FONTE") or "",
            row.get("NOME_INSERZIONISTA") or "",
            fixed,
            mobile,
            emails,
            row.get("FONTE_CONTATTO") or "",
            "SI" if row.get("STATO") == "NEW" and row_id(row) not in sent else "NO",
            row_id(row),
        ])
    return output


def col_name(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def xml_text(value):
    return escape(str(value), {'"': "&quot;"})


def build_xlsx(rows, destination):
    widths = [12, 9, 20, 34, 48, 16, 17, 10, 17, 22, 34, 20, 24, 20, 20, 28, 22, 10, 55]
    all_rows = [HEADERS] + rows
    links = []
    row_xml = []
    numeric_columns = {2, 6, 7, 8, 9}

    for row_index, values in enumerate(all_rows, start=1):
        cells = []
        for column_index, value in enumerate(values, start=1):
            ref = f"{col_name(column_index)}{row_index}"
            if row_index == 1:
                cells.append(f'<c r="{ref}" t="inlineStr" s="1"><is><t>{xml_text(value)}</t></is></c>')
            elif column_index in numeric_columns and isinstance(value, (int, float)):
                style = "3" if column_index in {6, 7} else "2"
                cells.append(f'<c r="{ref}" s="{style}"><v>{value}</v></c>')
            else:
                style = "4" if column_index == 19 and value else "0"
                cells.append(f'<c r="{ref}" t="inlineStr" s="{style}"><is><t>{xml_text(value)}</t></is></c>')
                if column_index == 19 and value:
                    links.append((ref, str(value)))
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    last_row = max(1, len(all_rows))
    cols = "".join(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>' for i, width in enumerate(widths, start=1))
    hyperlink_xml = ""
    if links:
        hyperlink_xml = "<hyperlinks>" + "".join(
            f'<hyperlink ref="{ref}" r:id="rId{index}"/>' for index, (ref, _) in enumerate(links, start=1)
        ) + "</hyperlinks>"

    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetViews><sheetView workbookViewId="0"><pane xSplit="3" ySplit="1" topLeftCell="D2" activePane="bottomRight" state="frozen"/></sheetView></sheetViews>
<sheetFormatPr defaultRowHeight="18"/><cols>{cols}</cols><sheetData>{"".join(row_xml)}</sheetData>
<autoFilter ref="A1:S{last_row}"/>{hyperlink_xml}
</worksheet>'''

    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="{xml_text(url)}" TargetMode="External"/>'
        for index, (_, url) in enumerate(links, start=1)
    ) + '</Relationships>'

    files = {
        "[Content_Types].xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>''',
        "_rels/.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>''',
        "docProps/app.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>F1 Seller Radar</Application></Properties>''',
        "docProps/core.xml": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>F1 Radar Acquisizione</dc:title><dc:creator>F1 Immobiliare</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{datetime.now(timezone.utc).isoformat()}</dcterms:created></cp:coreProperties>''',
        "xl/workbook.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="GIRO ACQUISIZIONE" sheetId="1" r:id="rId1"/></sheets></workbook>''',
        "xl/_rels/workbook.xml.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>''',
        "xl/styles.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="1"><numFmt numFmtId="164" formatCode="€ #,##0"/></numFmts><fonts count="3"><font><sz val="10"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Aptos"/></font><font><u/><color rgb="FF0563C1"/><sz val="10"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF174F2A"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFD9E2DC"/></left><right style="thin"><color rgb="FFD9E2DC"/></right><top style="thin"><color rgb="FFD9E2DC"/></top><bottom style="thin"><color rgb="FFD9E2DC"/></bottom><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"><alignment horizontal="center" vertical="top"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1"><alignment horizontal="right" vertical="top"/></xf><xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''',
        "xl/worksheets/sheet1.xml": sheet,
    }
    if links:
        files["xl/worksheets/_rels/sheet1.xml.rels"] = rels

    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def main():
    if not (EMAIL_USER and EMAIL_PASS and EMAIL_TO):
        print("Email non configurata: mancano F1_EMAIL_USER / F1_EMAIL_APP_PASSWORD / F1_EMAIL_TO")
        raise SystemExit(0)

    rows = load_rows()
    sent = load_sent()
    prepared = report_rows(rows, sent)
    new_rows = [row for row in rows if row.get("STATO") == "NEW" and row_id(row) and row_id(row) not in sent]
    date_label = datetime.now().strftime("%Y-%m-%d")
    report = DATA / f"F1_Radar_Acquisizione_{date_label}.xlsx"
    build_xlsx(prepared, report)

    message = EmailMessage()
    message["From"] = EMAIL_USER
    message["To"] = EMAIL_TO
    message["Subject"] = f"F1 Radar — report Excel {date_label} — {len(new_rows)} nuove"
    message.set_content(
        "F1 IMMOBILIARE — REPORT GIORNALIERO\n\n"
        f"Opportunita presenti nel file: {len(rows)}\n"
        f"Nuove opportunita: {len(new_rows)}\n\n"
        "Apri il file Excel allegato. I risultati sono ordinati per priorita e contengono i link cliccabili alle fonti.\n"
        "Prima di qualsiasi contatto: APRI FONTE E VERIFICA CONTATTO.\n"
    )
    message.add_attachment(
        report.read_bytes(),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=report.name,
    )

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.login(EMAIL_USER, EMAIL_PASS)
        smtp.send_message(message)

    for row in new_rows:
        sent.add(row_id(row))
    SENT.write_text(json.dumps({"sent_ids": sorted(sent)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report Excel inviato a {EMAIL_TO}: {len(rows)} opportunita, {len(new_rows)} nuove.")


if __name__ == "__main__":
    main()
