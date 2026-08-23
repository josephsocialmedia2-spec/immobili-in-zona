from io import BytesIO
import os
from pathlib import Path

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PRIMARY_PHONE = "+39 371 370 8294"
SECONDARY_PHONE = "+39 371 424 6300"


def _register_fonts() -> tuple[str, str]:
    """Use an embedded TrueType font when available, with a portable fallback."""
    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = (
        (windows_fonts / "arial.ttf", windows_fonts / "arialbd.ttf"),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    )
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            if "F1Sans" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("F1Sans", str(regular)))
                pdfmetrics.registerFont(TTFont("F1Sans-Bold", str(bold)))
                pdfmetrics.registerFontFamily("F1Sans", normal="F1Sans", bold="F1Sans-Bold", italic="F1Sans", boldItalic="F1Sans-Bold")
            return "F1Sans", "F1Sans-Bold"
    return "Helvetica", "Helvetica-Bold"


def _qr_image(site_url: str) -> Image:
    qr = qrcode.QRCode(box_size=5, border=2)
    qr.add_data(site_url)
    qr.make(fit=True)
    buffer = BytesIO()
    qr.make_image(fill_color="#111512", back_color="white").save(buffer, format="PNG")
    buffer.seek(0)
    return Image(buffer, width=27 * mm, height=27 * mm)


def generate_letter(practice: dict, destination: Path, site_url: str, confirmed_name: str = "") -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(destination), pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"F1 Immobiliare - {practice['id']}", author="F1 Immobiliare",
    )
    regular_font, bold_font = _register_fonts()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("F1Title", parent=styles["Title"], fontName=bold_font, fontSize=22, leading=26, textColor=colors.HexColor("#174F2A"), alignment=TA_CENTER)
    body = ParagraphStyle("F1Body", parent=styles["BodyText"], fontName=regular_font, fontSize=11.5, leading=17, spaceAfter=8)
    small = ParagraphStyle("F1Small", parent=body, fontSize=8.5, leading=12, textColor=colors.HexColor("#607066"))
    address = practice["normalized_address"]
    recipient = confirmed_name.strip() if confirmed_name.strip() else f"proprietario dell'immobile sito in {address}"
    story = [
        Paragraph("F1 IMMOBILIARE", title),
        Paragraph("Agenzia e strategia immobiliare", ParagraphStyle("sub", parent=small, alignment=TA_CENTER, fontSize=10)),
        Spacer(1, 14 * mm),
        Paragraph(f"Alla cortese attenzione del {recipient}", body),
        Spacer(1, 5 * mm),
        Paragraph("Gentile Proprietario/a,", body),
        Paragraph(
            "la contattiamo con riferimento esclusivo all'immobile indicato. F1 Immobiliare opera nella Valle di Susa con un metodo basato su verifica documentale, valorizzazione e selezione degli acquirenti realmente interessati.", body,
        ),
        Paragraph(
            "Se sta valutando una vendita, anche non immediata, possiamo offrirle un confronto riservato e senza impegno. Il ricontatto è totalmente volontario.", body,
        ),
        Spacer(1, 5 * mm),
        Table(
            [[Paragraph("IMMOBILE", small), Paragraph(address, body)], [Paragraph("ID PRATICA", small), Paragraph(practice["id"], body)]],
            colWidths=[35 * mm, 120 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F4EF")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#AEB7B0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D9E2DC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]),
        ),
        Spacer(1, 9 * mm),
        Table(
            [[Paragraph(f"<b>Contatti F1 Immobiliare</b><br/>{PRIMARY_PHONE}<br/>{SECONDARY_PHONE}<br/>{site_url}", body), _qr_image(site_url)]],
            colWidths=[125 * mm, 30 * mm],
            style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]),
        ),
        Spacer(1, 10 * mm),
        Paragraph(
            "Informativa sintetica: questa comunicazione è stata indirizzata all'immobile, senza diffusione pubblica di dati personali. Per non ricevere ulteriori comunicazioni è sufficiente contattarci indicando l'ID pratica; la richiesta verrà registrata come NON CONTATTARE.", small,
        ),
    ]
    doc.build(story)
    return destination
