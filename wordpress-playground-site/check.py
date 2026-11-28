"""Check blueprint.json and the files it loads (Python standard library only).

Usage:
  python check.py             run the checks
  python check.py --preview   also write preview.tmp/index.html: open it in a browser to start Playground
                              with the local files inlined (works before a push, shows PHP notices on screen)
"""
import base64
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = f"https://raw.githubusercontent.com/jinu041/data-automation-demos/main/{HERE.name}/"
LIVE = f"https://playground.wordpress.net/?blueprint-url={RAW}blueprint.json"
PAGES = {"home": "Home", "services": "Services", "pricing": "Pricing", "faq": "FAQ", "contact": "Contact"}
FORM = "Service booking request"
BLOCK = re.compile(r"<!-- (/?)wp:([a-z0-9/-]+) (?:(\{.*?\}) )?(/?)-->")

problems = []


def need(ok, message):
    if not ok:
        problems.append(message)


bp = json.loads((HERE / "blueprint.json").read_text(encoding="utf-8"))
steps = bp["steps"]
for i, s in enumerate(steps, 1):
    print(f"{i:2}. {s['step']:<15} {s.get('progress', {}).get('caption') or s.get('path') or s.get('username', '')}")

fetched = {}  # every writeFile step loads a file from site/ in this folder, by its raw GitHub URL
for s in steps:
    if s["step"] == "writeFile":
        url = s["data"]["url"]
        name = url.rsplit("/", 1)[1]
        need(url == f"{RAW}site/{name}", f"writeFile URL is not this folder's site/{name}: {url}")
        need(s["path"].endswith("/" + name), f"{s['path']} is not {name}")
        need((HERE / "site" / name).is_file(), f"missing site/{name}")
        fetched[name] = HERE / "site" / name
need(sorted(fetched) == sorted(p.name for p in (HERE / "site").iterdir()), "site/ and the writeFile steps list different files")

php = " ".join(s["code"] for s in steps if s["step"] == "runPHP")
for slug, title in PAGES.items():
    need(f"'{slug}' => '{title}'" in php and f"{slug}.html" in fetched, f"page {title} is not created from site/{slug}.html")
need(f"'title' => '{FORM}'" in php, "the booking form is not created")

for f in fetched.values():
    if f.suffix != ".html":
        continue
    html, stack = f.read_text(encoding="utf-8"), []
    for closing, name, attrs, self_closing in BLOCK.findall(html):
        if attrs:
            try:
                json.loads(attrs)
            except ValueError as e:
                problems.append(f"{f.name}: bad attributes on wp:{name}: {e}")
        if closing:
            need(stack and stack.pop() == name, f"{f.name}: /wp:{name} closes nothing")
        elif not self_closing:
            stack.append(name)
    need(not stack, f"{f.name}: blocks left open: {stack}")
    for target in re.findall(r'href="\{\{home_url\}\}/([^"]*)"', html):
        need(target.strip("/") in PAGES or target == "", f"{f.name}: link to a page that is not created: /{target}")

contact = (HERE / "site" / "contact.html").read_text(encoding="utf-8")
need(f'<!-- wp:shortcode -->\n[contact-form-7 title="{FORM}"]' in contact, "Contact page has no booking form shortcode")
json.loads((HERE / "site" / "styles.json").read_text(encoding="utf-8"))
need(LIVE in (HERE / "README.md").read_text(encoding="utf-8"), f"README does not link {LIVE}")
for png in sorted((HERE / "portfolio").glob("*.png")):  # 1600 x 1200, and no chunks beyond IHDR/IDAT/IEND
    data, i, chunks = png.read_bytes(), 8, set()
    while i < len(data):
        chunks.add(data[i + 4:i + 8].decode("latin-1"))
        i += 12 + int.from_bytes(data[i:i + 4], "big")
    need(data[16:24] == (1600).to_bytes(4, "big") + (1200).to_bytes(4, "big"), f"{png.name} is not 1600 x 1200")
    need(chunks <= {"IHDR", "IDAT", "IEND"}, f"{png.name} carries metadata chunks: {sorted(chunks)}")

if problems:
    sys.exit("\n".join(problems))
print(f"checks passed: {len(steps)} steps, pages {', '.join(PAGES.values())}, booking form shortcode, README live link, "
      f"{len(list((HERE / 'portfolio').glob('*.png')))} portfolio PNGs without metadata")

if "--preview" in sys.argv:
    for s in steps:  # same blueprint, with each fetched file inlined as text
        if s["step"] == "writeFile":
            s["data"] = fetched[s["path"].rsplit("/", 1)[1]].read_text(encoding="utf-8")
    steps.insert(0, {"step": "defineWpConfigConsts", "consts": {"WP_DEBUG": True, "WP_DEBUG_DISPLAY": True}})
    fragment = base64.b64encode(json.dumps(bp).encode("ascii")).decode()  # json.dumps escapes non-ASCII
    out = HERE / "preview.tmp" / "index.html"  # *.tmp is in the repo's .gitignore
    out.parent.mkdir(exist_ok=True)
    out.write_text('<!doctype html><meta charset="utf-8"><title>Preview before push</title>'
                   '<p>Opening WordPress Playground with the local files...</p>'
                   f'<script>location.replace("https://playground.wordpress.net/#{fragment}")</script>\n', encoding="utf-8")
    print(f"preview: {out} ({len(fragment):,} characters in the URL)")
