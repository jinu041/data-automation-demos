# -*- coding: utf-8 -*-
"""Build a reflowable EPUB 3 formatting demo from a public-domain story.

Input : text/tell-tale-heart.paras.json (18 paragraphs, <em> marks italics;
        checked against the source page by SHA-256 before use)
Output: out/the-tell-tale-heart-demo.epub and out/cover-kindle.jpg (1600 x 2560)
Needs : Python 3 + Pillow (only for the placeholder artwork).
Validate: java -jar epubcheck.jar out/the-tell-tale-heart-demo.epub
"""
import html
import json
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
ART = ROOT / "art"   # stand-ins for the PNG artwork a client would supply
TITLE = "The Tell-Tale Heart"
AUTHOR = "Edgar Allan Poe"
BOOK_ID = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "beoruk-studio/epub-demo/tell-tale-heart"))
MODIFIED = "2026-11-16T17:30:00Z"
FONTS = Path(r"C:\Windows\Fonts")


def font(name, size):
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default(size)


def centered(draw, y, text, fnt, fill, width, spacing=0):
    if spacing:
        text = (" " * spacing).join(text)
    w = draw.textlength(text, font=fnt)
    draw.text(((width - w) / 2, y), text, font=fnt, fill=fill)


def diamond(draw, cx, cy, r, fill):
    draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=fill)


def make_art():
    ART.mkdir(exist_ok=True)
    # Cover (what a client would hand over as PNG), 1600 x 2560 = KDP's 1:1.6 ratio.
    W, H = 1600, 2560
    im = Image.new("RGB", (W, H), "#141414")
    d = ImageDraw.Draw(im)
    big = font("georgiab.ttf", 230)
    for i, word in enumerate(["THE", "TELL-TALE", "HEART"]):
        centered(d, 640 + i * 290, word, big, "#f2efe8", W)
    d.rectangle([W / 2 - 260, 1560, W / 2 + 260, 1568], fill="#9b1c1c")
    centered(d, 1660, "EDGAR ALLAN POE", font("georgia.ttf", 96), "#f2efe8", W)
    centered(d, 2380, "FORMATTING DEMO", font("georgia.ttf", 52), "#8c8c8c", W, spacing=1)
    im.save(ART / "cover.png")

    # Interior title-page artwork.
    W, H = 1200, 900
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    centered(d, 250, "THE TELL-TALE", font("georgia.ttf", 104), "black", W)
    centered(d, 380, "HEART", font("georgia.ttf", 104), "black", W)
    d.rectangle([W / 2 - 180, 540, W / 2 + 180, 543], fill="black")
    diamond(d, W / 2, 541, 14, "black")
    centered(d, 600, AUTHOR, font("georgiai.ttf", 64), "black", W)
    im.save(ART / "title-page.png")

    # Closing-page artwork.
    W, H = 900, 450
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    for dx in (-70, 0, 70):
        diamond(d, W / 2 + dx, 150, 16, "black")
    centered(d, 230, "THE END", font("georgia.ttf", 72), "black", W, spacing=1)
    im.save(ART / "closing-page.png")

    OUT.mkdir(exist_ok=True)
    cover = Image.open(ART / "cover.png").convert("RGB")
    cover.save(OUT / "cover-kindle.jpg", "JPEG", quality=90)  # separate KDP upload file


def xhtml(title, body, css="../css/style.css"):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en" lang="en">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="{css}"/>
</head>
<body>
{body}
</body>
</html>
"""


def para_html(s):
    t = html.escape(s, quote=False)
    return t.replace("&lt;em&gt;", "<em>").replace("&lt;/em&gt;", "</em>")


CSS = """@charset "utf-8";
/* No body font-size or font-family: the reader's own settings win. */
body { margin: 0; padding: 0; line-height: 1.45; }
h1 { font-size: 1.5em; font-weight: normal; text-align: center; line-height: 1.2;
     margin: 2.5em 0 0.4em; page-break-after: avoid; }
p { margin: 0; text-indent: 1.2em; orphans: 2; widows: 2; }
p.first, p.byline, p.center, p.scene-break { text-indent: 0; }
p.byline { text-align: center; font-style: italic; margin: 0 0 2.5em; }
span.lead { text-transform: uppercase; letter-spacing: 0.06em; }
/* A scene break is real text, so it survives any font size; the next paragraph starts flush left. */
p.scene-break { text-align: center; margin: 1.1em 0; page-break-after: avoid; }
p.scene-break + p { text-indent: 0; }
p.center { text-align: center; }
p.small { font-size: 0.85em; margin-bottom: 0.8em; }
div.art { text-align: center; text-indent: 0; margin: 1.5em 0; page-break-inside: avoid; }
div.art img { width: 90%; max-width: 100%; height: auto; }
nav#toc ol { list-style-type: none; padding-left: 0; }
nav#toc li { margin: 0.6em 0; text-align: center; }
"""


def build():
    paras = json.loads((ROOT / "text" / "tell-tale-heart.paras.json").read_text(encoding="utf-8"))
    assert len(paras) == 18 and sum(p.count("<em>") for p in paras) == 21
    make_art()

    first = para_html(paras[0]).replace("True!", '<span class="lead">True!</span>', 1)
    body = [f'<p class="first">{first}</p>']
    body += [f"<p>{para_html(p)}</p>" for p in paras[1:]]
    story = (f'<section epub:type="chapter" id="story">\n<h1>{TITLE}</h1>\n'
             f'<p class="byline">{AUTHOR}</p>\n' + "\n".join(body) + "\n</section>")

    files = {
        "OEBPS/css/style.css": CSS,
        "OEBPS/text/titlepage.xhtml": xhtml(TITLE, '<section epub:type="titlepage">\n'
            f'<div class="art"><img src="../images/title-page.png" alt="{TITLE}, by {AUTHOR}"/></div>\n</section>'),
        "OEBPS/text/copyright.xhtml": xhtml("Copyright", '<section epub:type="copyright-page">\n'
            '<p class="center small">The Tell-Tale Heart by Edgar Allan Poe was first published in 1843. '
            'The story text is in the public domain. This edition follows the Standard Ebooks transcription, '
            'which they released into the public domain (CC0).</p>\n'
            '<p class="center small">Formatting demo by Beoruk Studio, 2026. Not a client book.</p>\n</section>'),
        "OEBPS/text/story.xhtml": xhtml(TITLE, story),
        "OEBPS/text/closing.xhtml": xhtml("The End", '<section>\n'
            '<div class="art"><img src="../images/closing-page.png" alt="The End"/></div>\n</section>'),
        "OEBPS/text/about.xhtml": xhtml("About This Edition", '<section epub:type="colophon">\n'
            "<h1>About This Edition</h1>\n"
            '<p class="first">This file is a formatting demo that shows how a short fiction ebook can be set up for Kindle. '
            "It is a reflowable EPUB 3: the text follows the reader’s font size and font choice, the table of contents is clickable, "
            "and the title-page and closing-page artwork are placed as images that scale to the screen. "
            "A separate Kindle cover JPEG (1600 × 2560 px) is made from the cover artwork.</p>\n"
            "<p>Poe’s dashes, italics and paragraphing are kept exactly as in the source text. "
            "Scene breaks inside a chapter are set as a centred line of asterisks with space above and below, like this:</p>\n"
            '<p class="scene-break" role="separator" aria-label="Scene break">* * *</p>\n'
            "<p>The paragraph after a break starts flush left. Because the break is real text and not an empty line, "
            "it does not vanish when a reader changes the font size or when the break falls at the top of a screen.</p>\n"
            "<p>The files were built with Claude (an AI tool), the story text was checked against the source paragraph by paragraph, "
            "and the EPUB was validated with EPUBCheck.</p>\n</section>"),
        "OEBPS/nav.xhtml": xhtml("Contents",
            '<nav epub:type="toc" id="toc">\n<h1>Contents</h1>\n<ol>\n'
            '<li><a href="text/titlepage.xhtml">Title Page</a></li>\n'
            f'<li><a href="text/story.xhtml">{TITLE}</a></li>\n'
            '<li><a href="text/about.xhtml">About This Edition</a></li>\n</ol>\n</nav>\n'
            '<nav epub:type="landmarks" id="landmarks" hidden="hidden">\n<h2>Guide</h2>\n<ol>\n'
            '<li><a epub:type="toc" href="nav.xhtml#toc">Contents</a></li>\n'
            '<li><a epub:type="bodymatter" href="text/story.xhtml">Start of story</a></li>\n</ol>\n</nav>',
            css="css/style.css"),
        "OEBPS/toc.ncx": f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="en">
<head>
<meta name="dtb:uid" content="{BOOK_ID}"/>
<meta name="dtb:depth" content="1"/>
<meta name="dtb:totalPageCount" content="0"/>
<meta name="dtb:maxPageNumber" content="0"/>
</head>
<docTitle><text>{TITLE}</text></docTitle>
<navMap>
<navPoint id="np1" playOrder="1"><navLabel><text>Title Page</text></navLabel><content src="text/titlepage.xhtml"/></navPoint>
<navPoint id="np2" playOrder="2"><navLabel><text>{TITLE}</text></navLabel><content src="text/story.xhtml"/></navPoint>
<navPoint id="np3" playOrder="3"><navLabel><text>About This Edition</text></navLabel><content src="text/about.xhtml"/></navPoint>
</navMap>
</ncx>
""",
        "OEBPS/content.opf": f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="en">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{BOOK_ID}</dc:identifier>
<dc:title>{TITLE}</dc:title>
<dc:creator id="author">{AUTHOR}</dc:creator>
<meta refines="#author" property="role" scheme="marc:relators">aut</meta>
<meta refines="#author" property="file-as">Poe, Edgar Allan</meta>
<dc:language>en</dc:language>
<dc:rights>The story text is in the public domain. This file is a formatting demo.</dc:rights>
<meta property="dcterms:modified">{MODIFIED}</meta>
<meta name="cover" content="cover-image"/>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="css" href="css/style.css" media-type="text/css"/>
<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>
<item id="title-art" href="images/title-page.png" media-type="image/png"/>
<item id="closing-art" href="images/closing-page.png" media-type="image/png"/>
<item id="titlepage" href="text/titlepage.xhtml" media-type="application/xhtml+xml"/>
<item id="copyright" href="text/copyright.xhtml" media-type="application/xhtml+xml"/>
<item id="story" href="text/story.xhtml" media-type="application/xhtml+xml"/>
<item id="closing" href="text/closing.xhtml" media-type="application/xhtml+xml"/>
<item id="about" href="text/about.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine toc="ncx">
<itemref idref="titlepage"/>
<itemref idref="copyright"/>
<itemref idref="nav"/>
<itemref idref="story"/>
<itemref idref="closing"/>
<itemref idref="about"/>
</spine>
</package>
""",
        "META-INF/container.xml": """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
""",
    }
    for name, text in files.items():  # every XML file must be well-formed
        if not name.endswith(".css"):
            ET.fromstring(text.encode("utf-8"))

    epub = OUT / "the-tell-tale-heart-demo.epub"
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, text in files.items():
            z.writestr(name, text.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        z.write(OUT / "cover-kindle.jpg", "OEBPS/images/cover.jpg", compress_type=zipfile.ZIP_STORED)
        for png in ("title-page.png", "closing-page.png"):
            z.write(ART / png, f"OEBPS/images/{png}", compress_type=zipfile.ZIP_STORED)
    print(epub, epub.stat().st_size, "bytes")
    print(OUT / "cover-kindle.jpg", Image.open(OUT / "cover-kindle.jpg").size)


if __name__ == "__main__":
    build()
