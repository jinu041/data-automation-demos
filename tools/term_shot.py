# Renders real command output as a terminal-style PNG (headless Chrome), for portfolio covers.
# Usage: python term_shot.py out.png "command line" stdout.txt [stderr.txt]   (a "$ " prompt is added)
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def main(out, cmd, stdout, stderr=None):
    so = Path(stdout).read_text(encoding="utf-8").rstrip("\n")
    se = Path(stderr).read_text(encoding="utf-8").rstrip("\n") if stderr else ""
    lines = so.count("\n") + se.count("\n") + 4
    width, height = 1400, 60 + lines * 34
    html = f"""<!doctype html><meta charset='utf-8'><style>
*{{margin:0;padding:0}} body{{width:{width}px;height:{height}px;background:#1E242B;font:24px/34px Consolas,'Cascadia Mono',monospace;color:#D7DEE5;padding:26px 30px;box-sizing:border-box;white-space:pre}}
.c{{color:#7FD1A8}} .e{{color:#F2B37A}}</style><div class='c'>$ {escape(cmd)}</div><div>{escape(so)}</div><div class='e'>{escape(se)}</div>"""
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "t.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={Path(tmp) / 'p'}",
                        "--force-device-scale-factor=1", f"--window-size={width},{height}", f"--screenshot={Path(out).resolve()}",
                        page.as_uri()], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    print("terminal shot", out)


if __name__ == "__main__":
    main(*sys.argv[1:])
