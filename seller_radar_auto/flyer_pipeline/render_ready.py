#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
import json
import qrcode

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
SIGNALS = ROOT / "signals" / "2026-08-18.json"
READY = ROOT / "ready" / "2026-08-18"
READY.mkdir(parents=True, exist_ok=True)

W, H = 1240, 1748  # A6 verticale, 300 dpi circa
BLACK = (15, 15, 15)
GRAY = (105, 105, 105)
LIGHT = (220, 220, 220)
WHITE = (255, 255, 255)

FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_COND = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"

def font(path, size):
    return ImageFont.truetype(path, size=size)

def wrap(draw, text, fnt, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        if draw.textbbox((0,0), test, font=fnt)[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def draw_centered_lines(draw, lines, fnt, box, fill=BLACK, spacing=8):
    x0,y0,x1,y1 = box
    heights = [draw.textbbox((0,0), ln, font=fnt)[3] for ln in lines]
    total = sum(heights) + spacing * max(0, len(lines)-1)
    y = y0 + (y1-y0-total)//2
    for ln, hh in zip(lines, heights):
        bb = draw.textbbox((0,0), ln, font=fnt)
        tw = bb[2]-bb[0]
        draw.text((x0 + (x1-x0-tw)//2, y), ln, font=fnt, fill=fill)
        y += hh + spacing

def fit_cover(img, size):
    return ImageOps.fit(img, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.42))

def make_qr():
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data("https://f1immobiliare.com/pages/contatti")
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")

def render(s):
    page = Image.new("RGB", (W,H), WHITE)
    d = ImageDraw.Draw(page)

    # Logo ufficiale in alto; nessun'altra grande campitura colorata.
    logo = Image.open(ASSETS / "logo_f1_official.jpg").convert("RGB")
    logo.thumbnail((550, 140), Image.Resampling.LANCZOS)
    page.paste(logo, (70, 45))

    # Localizzazione senza civico.
    loc = f"{s['comune']} — {s['via']} e zona limitrofa"
    d.text((70, 205), loc, font=font(FONT_REG, 31), fill=GRAY)
    d.line((70, 255, W-70, 255), fill=LIGHT, width=2)

    # Titolo principale.
    title_font = font(FONT_COND, 86)
    d.text((70, 300), "VUOI VENDERE CASA", font=title_font, fill=BLACK)
    d.text((70, 390), "IN QUESTA ZONA?", font=title_font, fill=BLACK)

    # Problema commerciale sintetico.
    problem_font = font(FONT_BOLD, 38)
    problem_lines = wrap(d, s['problema'], problem_font, W-140)
    y = 515
    for ln in problem_lines[:3]:
        d.text((70, y), ln, font=problem_font, fill=BLACK)
        y += 51

    # Seller signal in contenitore bianco, bordo nero sottile.
    box_y0, box_y1 = 700, 900
    d.rounded_rectangle((70, box_y0, W-70, box_y1), radius=22, fill=WHITE, outline=BLACK, width=3)
    d.text((105, box_y0+25), "RILEVATO NELLA ZONA", font=font(FONT_BOLD, 26), fill=GRAY)
    signal_font = font(FONT_COND, 47)
    sig_lines = wrap(d, s['signal_label'], signal_font, W-210)
    draw_centered_lines(d, sig_lines[:3], signal_font, (100, box_y0+58, W-100, box_y1-18), BLACK, 6)

    # CTA principale.
    cta_y0, cta_y1 = 940, 1060
    d.rounded_rectangle((70, cta_y0, W-70, cta_y1), radius=20, fill=WHITE, outline=BLACK, width=4)
    cta = "RICHIEDI UNA VALUTAZIONE GRATUITA"
    cta_font = font(FONT_COND, 43)
    draw_centered_lines(d, wrap(d, cta, cta_font, W-190), cta_font, (90, cta_y0+8, W-90, cta_y1-8), BLACK, 4)

    # Parte inferiore: prima analisi gratuita, massimo tre elementi.
    d.text((70, 1110), "PRIMA ANALISI GRATUITA", font=font(FONT_BOLD, 29), fill=BLACK)
    bullet_font = font(FONT_REG, 27)
    for i, txt in enumerate(["Valore di mercato", "Immobili concorrenti", "Strategia di vendita"]):
        yy = 1160 + i*44
        d.ellipse((73, yy+10, 84, yy+21), fill=BLACK)
        d.text((100, yy), txt, font=bullet_font, fill=BLACK)

    # QR nero su bianco, minimo equivalente ~22 mm.
    qr = make_qr().resize((265,265), Image.Resampling.NEAREST)
    qr_x, qr_y = 70, 1335
    page.paste(qr, (qr_x, qr_y))
    qr_label_font = font(FONT_BOLD, 18)
    qr_label = ["SCANSIONA PER RICHIEDERE", "LA VALUTAZIONE GRATUITA"]
    yy = qr_y + 267
    for ln in qr_label:
        d.text((qr_x, yy), ln, font=qr_label_font, fill=BLACK)
        yy += 23

    # Team reale in basso a destra, dimensione contenuta.
    team = Image.open(ASSETS / "team_joseph_francesca.jpg").convert("RGB")
    team = fit_cover(team, (310, 405))
    tx, ty = W-70-310, 1280
    page.paste(team, (tx, ty))

    # Contatti essenziali, senza sovraccarico.
    contact_x = 380
    d.text((contact_x, 1350), "Joseph Malafronte", font=font(FONT_BOLD, 25), fill=BLACK)
    d.text((contact_x, 1385), "+39 371 370 8294", font=font(FONT_BOLD, 31), fill=BLACK)
    d.text((contact_x, 1440), "Francesca Aurigemma", font=font(FONT_BOLD, 23), fill=BLACK)
    d.text((contact_x, 1473), "+39 371 424 6300", font=font(FONT_REG, 25), fill=BLACK)
    d.text((contact_x, 1530), "f1immobiliaresusa@outlook.it", font=font(FONT_REG, 20), fill=BLACK)

    base = f"F1_SellerSignal_{s['filename_slug']}_2026-08-18"
    png = READY / f"{base}.png"
    pdf = READY / f"{base}.pdf"
    page.save(png, "PNG", dpi=(300,300), optimize=True)
    page.save(pdf, "PDF", resolution=300.0)
    return png.name, pdf.name

def main():
    signals = json.loads(SIGNALS.read_text(encoding="utf-8"))
    files = []
    for s in signals:
        files.extend(render(s))
    (READY / "GENERATED.json").write_text(json.dumps({"count": len(signals), "files": files}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generate {len(signals)} grafiche, {len(files)} file finali.")

if __name__ == "__main__":
    main()
