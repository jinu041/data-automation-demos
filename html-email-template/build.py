"""Check email.html, write ready-to-paste copies for Mailchimp, Klaviyo and Brevo, and render screenshots.

Usage: python build.py   (screenshots need Google Chrome; set CHROME to its path if it isn't found)
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
SRC = (HERE / "email.html").read_text(encoding="utf-8")

# Each platform's own merge tags (from their docs). Mailchimp's first-name fallback is set in the audience settings.
TAGS = {
    "mailchimp": {"FIRST_NAME": "*|FNAME|*", "UNSUBSCRIBE_URL": "*|UNSUB|*", "WEB_VIEW_URL": "*|ARCHIVE|*"},
    "klaviyo": {"FIRST_NAME": "{{ first_name|default:'there' }}", "UNSUBSCRIBE_URL": "{% unsubscribe_link %}",
                "WEB_VIEW_URL": "{% web_view_link %}"},
    "brevo": {"FIRST_NAME": '{{ contact.FIRSTNAME|default:"there" }}', "UNSUBSCRIBE_URL": "{{ unsubscribe }}",
              "WEB_VIEW_URL": "{{ mirror }}"},
}
PREVIEW = {"FIRST_NAME": "Sam", "UNSUBSCRIBE_URL": "https://mossgate.example/unsubscribe",
           "WEB_VIEW_URL": "https://mossgate.example/view"}


def check(html):
    problems = []
    size = len(html.encode("utf-8"))
    if size >= 102 * 1024:
        problems.append(f"{size} bytes: Gmail clips messages over about 102 KB")
    for tag in ("<script", "<form", "<iframe", "<video", 'rel="stylesheet"'):
        if tag in html.lower():
            problems.append(f"{tag} is stripped or blocked by most inboxes")
    for t in re.findall(r"<table\b[^>]*>", html):
        if 'role="presentation"' not in t:
            problems.append(f"layout table without role=presentation: {t[:60]}")
    for t in re.findall(r"<img\b[^>]*>", html):
        if "alt=" not in t:
            problems.append(f"image without alt text: {t[:60]}")
    for href in re.findall(r'href="([^"]*)"', html):
        if not (href.startswith("https://mossgate.example/") or re.fullmatch(r"%%[A-Z_]+%%", href)):
            problems.append(f"link goes nowhere or to the wrong place: {href!r}")
    if 'display:none' not in html.split("<table", 1)[0]:
        problems.append("no preheader before the first table")
    used = set(re.findall(r"%%([A-Z_]+)%%", html))
    if used != set(PREVIEW):
        problems.append(f"placeholders {sorted(used)} don't match {sorted(PREVIEW)}")
    for must in ("%%UNSUBSCRIBE_URL%%", "Sample Lane"):  # unsubscribe link and postal address (CAN-SPAM)
        if must not in html:
            problems.append(f"footer is missing {must}")
    return problems


def fill(html, tags):
    for key, value in tags.items():
        html = html.replace(f"%%{key}%%", value)
    assert "%%" not in html, "unfilled placeholder"
    return html


def png_chunks(path):
    b, i, out = path.read_bytes(), 8, []
    while i < len(b):
        n = int.from_bytes(b[i:i + 4], "big")
        out.append(b[i + 4:i + 8].decode("latin-1"))
        i += 12 + n
    return out


def shoot(html, out, width, height, dark=False):
    chrome = os.environ.get("CHROME") or shutil.which("chrome") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not Path(chrome).exists():
        print("Chrome not found, screenshots skipped")
        return
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "preview.html").write_text(html, encoding="utf-8")
        # Chrome windows don't go below about 500 px, so the email sits in an iframe of the exact width.
        host = Path(td) / "host.html"
        host.write_text('<!doctype html><body style="margin:0"><iframe src="preview.html" '
                        f'style="border:0;display:block;width:{width}px;height:{height}px"></iframe>', encoding="utf-8")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={Path(td) / 'p'}",
                        "--force-device-scale-factor=2", f"--blink-settings=preferredColorScheme={0 if dark else 1}",
                        f"--window-size={max(width, 600)},{height}", f"--screenshot={out}", host.as_uri()],
                        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    try:  # cut to the email width and trim the empty page colour below the footer
        from PIL import Image
        im = Image.open(out).convert("RGB").crop((0, 0, width * 2, height * 2))
        bg, (w, h) = im.getpixel((0, im.height - 1)), im.size
        y = h - 1
        while y > 0 and all(im.getpixel((x, y)) == bg for x in range(0, w, 4)):
            y -= 1
        im.crop((0, 0, w, min(h, y + 48))).save(out, optimize=True)
    except ImportError:
        pass
    extra = [c for c in png_chunks(out) if c in ("tEXt", "iTXt", "zTXt", "eXIf", "tIME")]
    assert not extra, (out, extra)
    print(out.relative_to(HERE), "ok")


problems = check(SRC)
if problems:
    sys.exit("\n".join(problems))
print("checks passed:", len(SRC.encode("utf-8")), "bytes, 0 problems")
(HERE / "dist").mkdir(exist_ok=True)
for name, tags in TAGS.items():
    (HERE / "dist" / f"{name}.html").write_bytes(fill(SRC, tags).encode("utf-8"))
    print(f"dist/{name}.html ok")
(HERE / "screenshots").mkdir(exist_ok=True)
preview = fill(SRC, PREVIEW)
shoot(preview, HERE / "screenshots" / "desktop.png", 680, 1500)
shoot(preview, HERE / "screenshots" / "mobile.png", 375, 2000)
shoot(preview, HERE / "screenshots" / "dark.png", 680, 1500, dark=True)
