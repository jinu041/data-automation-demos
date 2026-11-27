"""KDP cover package sample for a made-up book (the same book as the 5x8 interior sample).

Builds, from SVG drawn here, with headless Chrome:
  out/cover-print.pdf        full paperback cover: back + spine + front, 0.125 in bleed, 5 x 8 trim, 120 pages white paper
  out/cover-guides.png       the same cover with trim, spine, safe-area and barcode guides (for checking, not for upload)
  out/audiobook-2400.png     2400 x 2400 square audiobook cover
  out/aplus-header-970x600.png, out/aplus-banner-970x300.png, out/aplus-tile-1..3-300x300.png   A+ Content images
  out/preview.png            1600 x 1200 overview for a portfolio
Then checks page size, embedded fonts, metadata and image sizes.
Usage: python build.py   (needs Google Chrome; set CHROME if it isn't in the default place; pip install pymupdf pillow)
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

# KDP numbers (paperback, white paper): spine = pages x 0.002252 in; bleed 0.125 in; spine text needs more than 79 pages.
TRIM_W, TRIM_H, BLEED, PAGES, PER_PAGE = 5.0, 8.0, 0.125, 120, 0.002252
SPINE = PAGES * PER_PAGE
PT = 72.0
W = (2 * TRIM_W + SPINE + 2 * BLEED) * PT
H = (TRIM_H + 2 * BLEED) * PT
B = BLEED * PT
BACK_X, SPINE_X = B, B + TRIM_W * PT
FRONT_X = SPINE_X + SPINE * PT
SAFE = 0.375 * PT  # text stays this far inside the trim (KDP asks for at least 0.125 in)

NAVY, NAVY2, AMBER, CREAM = "#13233f", "#1b3157", "#f2a541", "#f4efe4"
SERIF, SANS = "Georgia", "Segoe UI"
TITLE = ["Meetings", "That End", "on Time"]
SUBTITLE = "A Short Field Guide for Team Leads"
AUTHOR = "SAMPLE AUTHOR"


def clock(cx, cy, r, stroke):
    """Clock face with a 25-minute amber arc and one hand."""
    import math
    ticks = []
    for i in range(12):
        a = math.radians(i * 30)
        r1, r2 = r * (0.86 if i % 3 else 0.80), r * 0.93
        ticks.append(f'<line x1="{cx + r1 * math.sin(a):.2f}" y1="{cy - r1 * math.cos(a):.2f}" '
                     f'x2="{cx + r2 * math.sin(a):.2f}" y2="{cy - r2 * math.cos(a):.2f}" '
                     f'stroke="{CREAM}" stroke-opacity=".45" stroke-width="{stroke * .5:.2f}" stroke-linecap="round"/>')
    end = math.radians(150)  # 25 minutes
    ex, ey = cx + r * math.sin(end), cy - r * math.cos(end)
    hx, hy = cx + r * 0.62 * math.sin(end), cy - r * 0.62 * math.cos(end)
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{CREAM}" stroke-opacity=".22" stroke-width="{stroke * .6:.2f}"/>'
            + "".join(ticks)
            + f'<path d="M {cx} {cy - r} A {r} {r} 0 0 1 {ex:.2f} {ey:.2f}" fill="none" stroke="{AMBER}" '
              f'stroke-width="{stroke * 2.2:.2f}" stroke-linecap="round"/>'
            + f'<line x1="{cx}" y1="{cy}" x2="{hx:.2f}" y2="{hy:.2f}" stroke="{CREAM}" stroke-width="{stroke:.2f}" stroke-linecap="round"/>'
            + f'<circle cx="{cx}" cy="{cy}" r="{stroke * 1.6:.2f}" fill="{AMBER}"/>')


def front(x0, y0, s=1.0):
    """Front panel art and type for a 360 x 576 pt trim box at (x0, y0), scaled by s."""
    g = [f'<g transform="translate({x0} {y0}) scale({s})">',
         clock(180, 160, 96, 3.2),
         f'<rect x="{SAFE}" y="300" width="46" height="4" fill="{AMBER}"/>']
    for i, line in enumerate(TITLE):
        g.append(f'<text x="{SAFE}" y="{352 + i * 46}" font-family="{SERIF}" font-weight="700" font-size="44" fill="{CREAM}">{line}</text>')
    g.append(f'<text x="{SAFE}" y="{352 + 2 * 46 + 38}" font-family="{SANS}" font-size="14" fill="{AMBER}">{SUBTITLE}</text>')
    g.append(f'<text x="{SAFE}" y="{576 - SAFE}" font-family="{SANS}" font-weight="600" font-size="11" letter-spacing="3" fill="{CREAM}">{AUTHOR}</text>')
    g.append("</g>")
    return "".join(g)


def back(x0, y0):
    lines = ["Most meetings run long for the same few reasons:",
             "no clear decision, too many people, and nobody",
             "keeping time. This short field guide gives team",
             "leads a simple way to fix all three, with",
             "checklists you can copy into your next invite."]
    bullets = ["Book 25 or 50 minutes, not 30 or 60",
               "Put the decision in the invitation",
               "End five minutes early and write down",
               "what was agreed"]
    g = [f'<g transform="translate({x0} {y0})">']
    for i, t in enumerate(["Twenty-five minutes.", "One decision.", "Then back to work."]):
        g.append(f'<text x="{SAFE}" y="{SAFE + 34 + i * 30}" font-family="{SERIF}" font-weight="700" font-size="24" fill="{CREAM}">{t}</text>')
    for i, t in enumerate(lines):
        g.append(f'<text x="{SAFE}" y="{SAFE + 150 + i * 17}" font-family="{SANS}" font-size="11" fill="{CREAM}" fill-opacity=".92">{t}</text>')
    y = SAFE + 262
    for i, t in enumerate(bullets):
        if i != 3:
            g.append(f'<rect x="{SAFE}" y="{y + i * 22 - 8}" width="7" height="7" fill="{AMBER}"/>')
        g.append(f'<text x="{SAFE + 16}" y="{y + i * 22 - (6 if i == 3 else 0)}" font-family="{SANS}" font-size="11" fill="{CREAM}">{t}</text>')
    g.append(f'<text x="{SAFE}" y="{576 - SAFE - 4}" font-family="{SANS}" font-size="7.5" fill="{CREAM}" fill-opacity=".6">Portfolio sample · not a real book</text>')
    g.append("</g>")
    return "".join(g)


def spine_text():
    cx = SPINE_X + SPINE * PT / 2
    return (f'<text transform="translate({cx - 2.8:.2f} {B + SAFE}) rotate(90)" font-family="{SANS}" font-weight="600" '
            f'font-size="8" letter-spacing="1.2" fill="{NAVY}">MEETINGS THAT END ON TIME</text>'
            f'<text transform="translate({cx - 2.8:.2f} {B + TRIM_H * PT - SAFE - 62}) rotate(90)" font-family="{SANS}" '
            f'font-size="7" letter-spacing="1" fill="{NAVY}">SAMPLE AUTHOR</text>')


def cover_svg(guides=False):
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W / PT:.4f}in" height="{H / PT:.4f}in" viewBox="0 0 {W:.3f} {H:.3f}">',
             f'<rect width="{W:.3f}" height="{H:.3f}" fill="{NAVY}"/>',
             f'<rect x="{BACK_X - B:.3f}" y="0" width="{TRIM_W * PT + B:.3f}" height="{H:.3f}" fill="{NAVY2}"/>',
             f'<rect x="{SPINE_X:.3f}" y="0" width="{SPINE * PT:.3f}" height="{H:.3f}" fill="{AMBER}"/>',
             back(BACK_X, B), spine_text(), front(FRONT_X, B)]
    if guides:
        bx0 = SPINE_X - 0.25 * PT - 2 * PT  # barcode area: 2 x 1.2 in, 0.25 in from the trim, lower right of the back
        by0 = B + TRIM_H * PT - 0.25 * PT - 1.2 * PT
        dash = 'stroke-dasharray="4 3"'
        parts += [f'<rect x="{B}" y="{B}" width="{W - 2 * B:.3f}" height="{TRIM_H * PT}" fill="none" stroke="#ff4d4d" stroke-width=".8" {dash}/>',
                  f'<line x1="{SPINE_X:.3f}" y1="0" x2="{SPINE_X:.3f}" y2="{H}" stroke="#36d1ff" stroke-width=".8" {dash}/>',
                  f'<line x1="{FRONT_X:.3f}" y1="0" x2="{FRONT_X:.3f}" y2="{H}" stroke="#36d1ff" stroke-width=".8" {dash}/>']
        for x in (BACK_X, FRONT_X):
            parts.append(f'<rect x="{x + SAFE:.3f}" y="{B + SAFE}" width="{TRIM_W * PT - 2 * SAFE:.3f}" height="{TRIM_H * PT - 2 * SAFE}" '
                         f'fill="none" stroke="#7CFC7C" stroke-width=".6" {dash}/>')
        parts += [f'<rect x="{bx0:.3f}" y="{by0:.3f}" width="{2 * PT}" height="{1.2 * PT}" fill="#ffffff" fill-opacity=".85"/>',
                  f'<text x="{bx0 + 72:.3f}" y="{by0 + 46:.3f}" text-anchor="middle" font-family="{SANS}" font-size="9" fill="#333">barcode area (KDP adds it)</text>',
                  f'<text x="{B + 6}" y="{B - 2}" font-family="{SANS}" font-size="6.5" fill="#ff4d4d">trim</text>',
                  f'<text x="{SPINE_X + 2:.3f}" y="{H - 2}" font-family="{SANS}" font-size="6.5" fill="#36d1ff">spine {SPINE:.4f} in</text>']
    parts.append("</svg>")
    return "".join(parts)


def audiobook_svg():
    s = 2400
    t = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{s}" height="{s}" viewBox="0 0 {s} {s}">',
         f'<rect width="{s}" height="{s}" fill="{NAVY}"/>', clock(1200, 760, 470, 14),
         f'<text x="1200" y="1600" text-anchor="middle" font-family="{SERIF}" font-weight="700" font-size="200" fill="{CREAM}">Meetings That</text>',
         f'<text x="1200" y="1820" text-anchor="middle" font-family="{SERIF}" font-weight="700" font-size="200" fill="{CREAM}">End on Time</text>',
         f'<text x="1200" y="1975" text-anchor="middle" font-family="{SANS}" font-size="72" fill="{AMBER}">{SUBTITLE}</text>',
         f'<text x="1200" y="2230" text-anchor="middle" font-family="{SANS}" font-weight="600" font-size="60" letter-spacing="14" fill="{CREAM}">{AUTHOR}</text>',
         "</svg>"]
    return "".join(t)


def aplus_header_svg():
    t = [f'<svg xmlns="http://www.w3.org/2000/svg" width="970" height="600" viewBox="0 0 970 600">',
         f'<rect width="970" height="600" fill="{CREAM}"/>',
         f'<rect x="70" y="72" width="282" height="451" fill="#000" fill-opacity=".18" transform="translate(10 12)"/>',
         f'<svg x="70" y="72" width="282" height="451" viewBox="0 0 360 576"><rect width="360" height="576" fill="{NAVY}"/>{front(0, 0)}</svg>',
         f'<rect x="420" y="150" width="56" height="5" fill="{AMBER}"/>',
         f'<text x="420" y="210" font-family="{SERIF}" font-weight="700" font-size="40" fill="{NAVY}">Shorter meetings start</text>',
         f'<text x="420" y="258" font-family="{SERIF}" font-weight="700" font-size="40" fill="{NAVY}">before the invite goes out</text>']
    for i, line in enumerate(["One decision per meeting, written in the invite.",
                              "Fewer people, a named timekeeper, a hard stop.",
                              "Checklists you can copy straight into your calendar."]):
        t.append(f'<text x="420" y="{330 + i * 38}" font-family="{SANS}" font-size="21" fill="{NAVY}" fill-opacity=".85">{line}</text>')
    t.append("</svg>")
    return "".join(t)


def aplus_banner_svg():
    cols = [("Short chapters", "you can read between", "two meetings"),
            ("Checklists", "to copy into your", "next invitation"),
            ("A one-page plan", "for the meeting you", "dread the most")]
    t = [f'<svg xmlns="http://www.w3.org/2000/svg" width="970" height="300" viewBox="0 0 970 300">',
         f'<rect width="970" height="300" fill="{NAVY}"/>',
         f'<text x="485" y="70" text-anchor="middle" font-family="{SERIF}" font-weight="700" font-size="34" fill="{CREAM}">What\'s inside</text>']
    for i, (h, a, b) in enumerate(cols):
        x = 170 + i * 315
        t += [f'<rect x="{x - 24}" y="120" width="48" height="4" fill="{AMBER}"/>',
              f'<text x="{x}" y="168" text-anchor="middle" font-family="{SANS}" font-weight="600" font-size="24" fill="{CREAM}">{h}</text>',
              f'<text x="{x}" y="204" text-anchor="middle" font-family="{SANS}" font-size="18" fill="{CREAM}" fill-opacity=".8">{a}</text>',
              f'<text x="{x}" y="230" text-anchor="middle" font-family="{SANS}" font-size="18" fill="{CREAM}" fill-opacity=".8">{b}</text>']
    t.append("</svg>")
    return "".join(t)


def tile_svg(i):
    head = f'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300"><rect width="300" height="300" fill="{NAVY}"/>'
    if i == 1:
        art = (f'<text x="150" y="150" text-anchor="middle" font-family="{SERIF}" font-weight="700" font-size="110" fill="{AMBER}">25</text>'
               f'<text x="150" y="205" text-anchor="middle" font-family="{SANS}" font-size="22" fill="{CREAM}">minutes, not 30</text>')
    elif i == 2:
        art = (f'<rect x="85" y="70" width="130" height="90" rx="6" fill="none" stroke="{CREAM}" stroke-width="5"/>'
               f'<path d="M 88 74 L 150 122 L 212 74" fill="none" stroke="{AMBER}" stroke-width="5" stroke-linejoin="round"/>'
               f'<text x="150" y="210" text-anchor="middle" font-family="{SANS}" font-size="22" fill="{CREAM}">The decision goes</text>'
               f'<text x="150" y="238" text-anchor="middle" font-family="{SANS}" font-size="22" fill="{CREAM}">in the invite</text>')
    else:
        art = (clock(150, 112, 62, 2.4)
               + f'<text x="150" y="222" text-anchor="middle" font-family="{SANS}" font-size="22" fill="{CREAM}">End five minutes early</text>')
    return head + art + "</svg>"


def chrome():
    c = os.environ.get("CHROME") or shutil.which("chrome") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not Path(c).exists():
        raise SystemExit("Chrome not found; set CHROME")
    return c


def page(svg, size_css=None):
    style = "html,body{margin:0;padding:0;background:#fff}svg{display:block}"
    if size_css:
        style += "@page{size:%s;margin:0}" % size_css
    return f'<!doctype html><html><head><meta charset="utf-8"><title>sample</title><style>{style}</style></head><body>{svg}</body></html>'


def run_chrome(args, html, td):
    src = Path(td) / "page.html"
    src.write_text(html, encoding="utf-8")
    subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={Path(td) / 'p'}",
                    *args, src.as_uri()], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)


def to_pdf(svg, out):
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "raw.pdf"
        run_chrome(["--no-pdf-header-footer", f"--print-to-pdf={raw}"], page(svg, f"{W / PT:.4f}in {H / PT:.4f}in"), td)
        # Chrome rounds the page size by up to ~0.5 pt; KDP wants the exact calculated size, so place it on an exact page.
        src, dst = fitz.open(raw), fitz.open()
        pg = dst.new_page(width=W, height=H)
        pg.show_pdf_page(pg.rect, src, 0, keep_proportion=False)
        dst.set_metadata({"title": "Meetings That End on Time - cover sample", "author": "", "subject": "", "keywords": "",
                          "creator": "", "producer": ""})
        dst.save(out, garbage=4, deflate=True)
        src.close()
        dst.close()


def to_png(svg, out, w, h, scale=1):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "shot.png"
        run_chrome([f"--force-device-scale-factor={scale}", f"--window-size={max(w, 600)},{max(h, 600)}", f"--screenshot={tmp}"],
                   page(svg), td)
        Image.open(tmp).convert("RGB").crop((0, 0, w * scale, h * scale)).save(out, optimize=True)  # Pillow writes no text chunks


def main():
    OUT.mkdir(exist_ok=True)
    pdf = OUT / "cover-print.pdf"
    to_pdf(cover_svg(), pdf)
    to_png(cover_svg(guides=True).replace(f'width="{W / PT:.4f}in" height="{H / PT:.4f}in"', f'width="{round(W / PT * 150)}" height="{round(H / PT * 150)}"'),
           OUT / "cover-guides.png", round(W / PT * 150), round(H / PT * 150))
    to_png(audiobook_svg(), OUT / "audiobook-2400.png", 2400, 2400)
    to_png(aplus_header_svg(), OUT / "aplus-header-970x600.png", 970, 600)
    to_png(aplus_banner_svg(), OUT / "aplus-banner-970x300.png", 970, 300)
    for i in (1, 2, 3):
        to_png(tile_svg(i), OUT / f"aplus-tile-{i}-300x300.png", 300, 300)

    # checks
    doc = fitz.open(pdf)
    assert doc.page_count == 1, doc.page_count
    r = doc[0].rect
    assert abs(r.width - W) < 0.01 and abs(r.height - H) < 0.01, (r, W, H)
    fonts = doc[0].get_fonts(full=True)
    assert fonts and all(f[1] != "n/a" for f in fonts), fonts
    assert not any((doc.metadata.get(k) or "").strip() for k in ("author", "creator", "producer")), doc.metadata
    names = sorted({f[3].split("+")[-1] for f in fonts})
    doc.close()
    for name, size in [("audiobook-2400.png", (2400, 2400)), ("aplus-header-970x600.png", (970, 600)),
                       ("aplus-banner-970x300.png", (970, 300))] + [(f"aplus-tile-{i}-300x300.png", (300, 300)) for i in (1, 2, 3)]:
        assert Image.open(OUT / name).size == size, name
    print(f"cover {W / PT:.4f} x {H / PT:.4f} in (spine {SPINE:.4f} in for {PAGES} pages), 1 page, fonts embedded: {', '.join(names)}")

    # 1600 x 1200 overview
    from PIL import ImageDraw, ImageFont
    sheet = Image.new("RGB", (1600, 1200), (236, 232, 222))
    cov = Image.open(OUT / "cover-guides.png")
    cov = cov.resize((1060, round(cov.height * 1060 / cov.width)), Image.LANCZOS)
    sheet.paste(cov, (40, 40))
    sheet.paste(Image.open(OUT / "audiobook-2400.png").resize((430, 430), Image.LANCZOS), (1130, 40))
    sheet.paste(Image.open(OUT / "aplus-banner-970x300.png").resize((430, 133), Image.LANCZOS), (1130, 500))
    for i in (1, 2, 3):
        sheet.paste(Image.open(OUT / f"aplus-tile-{i}-300x300.png").resize((135, 135), Image.LANCZOS), (1130 + (i - 1) * 147, 660))
    sheet.paste(Image.open(OUT / "aplus-header-970x600.png").resize((470, 291), Image.LANCZOS), (40, 40 + cov.height + 28))
    d = ImageDraw.Draw(sheet)
    big = ImageFont.truetype(r"C:\Windows\Fonts\seguisb.ttf", 30)
    small = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 22)
    x, y = 545, 40 + cov.height + 40
    d.text((x, y), "KDP cover package (sample, made-up book)", font=big, fill=(19, 35, 63))
    for i, line in enumerate([f"Paperback cover: back + spine + front, 5 x 8 trim, 0.125 in bleed,",
                              f"spine {SPINE:.4f} in for {PAGES} pages (white paper), print PDF with fonts embedded",
                              "Guides: trim, spine folds, 0.375 in safe area, barcode area",
                              "Audiobook cover 2400 x 2400 px",
                              "A+ Content: 970 x 600 header, 970 x 300 banner, three 300 x 300 tiles"]):
        d.text((x, y + 50 + i * 34), line, font=small, fill=(40, 50, 70))
    sheet.save(OUT / "preview.png", optimize=True)
    print("all files in", OUT)


if __name__ == "__main__":
    main()
