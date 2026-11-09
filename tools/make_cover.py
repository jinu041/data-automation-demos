# Makes a 1600x1200 portfolio cover from real screenshots (headless Chrome).
# Usage: python make_cover.py out.png "Title" "Subtitle" "bullet 1|bullet 2|..." shot1.png [shot2.png|""] ["data note"]
#   shot1 is shown full width (or left of the bullets when it's tall); shot2 (optional) sits bottom-left next to
#   the bullets. The data note goes in the footer (default "made-up data").
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def aspect(png):
    head = Path(png).read_bytes()[16:24]  # PNG IHDR: width, height
    return int.from_bytes(head[:4], "big") / int.from_bytes(head[4:], "big")


def main(out, title, sub, bullets, shot1, shot2=None, data_note="made-up data"):
    shot2 = shot2 or None  # "" means no second screenshot
    lis = "".join(f"<li>{escape(b)}</li>" for b in bullets.split("|") if b)
    if not shot2 and aspect(shot1) < 2:  # tall screenshot: image on the left, bullets on the right
        body = f"<div class='row'><img class='s3' src='{Path(shot1).resolve().as_uri()}'><ul>{lis}</ul></div>"
    else:
        low = (f"<div class='row'><img class='s2' src='{Path(shot2).resolve().as_uri()}'><ul>{lis}</ul></div>" if shot2
               else f"<ul class='wide'>{lis}</ul>")
        body = f"<img class='s1' src='{Path(shot1).resolve().as_uri()}'>{low}"
    html = f"""<!doctype html><meta charset='utf-8'><style>
*{{margin:0;padding:0;box-sizing:border-box}} body{{width:1600px;height:1200px;overflow:hidden;background:#F4F1EC;font-family:'Segoe UI',Arial,sans-serif;color:#1F2A33}}
h1{{font-size:64px;font-weight:800;letter-spacing:-1px;margin:64px 70px 0}} .sub{{font-size:30px;color:#5B6670;margin:14px 70px 0}}
.s1{{display:block;width:1460px;margin:40px 70px 0;border:2px solid #CDD5DC;border-radius:14px;box-shadow:0 10px 26px rgba(31,42,51,.12);background:#fff}}
.row{{display:flex;gap:44px;margin:36px 70px 0;align-items:flex-start}} .s2{{width:820px;border:2px solid #CDD5DC;border-radius:14px;background:#fff;box-shadow:0 10px 26px rgba(31,42,51,.12)}}
.s3{{width:1000px;max-height:880px;object-fit:contain;object-position:top left;border:2px solid #CDD5DC;border-radius:14px;background:#fff;box-shadow:0 10px 26px rgba(31,42,51,.12)}}
ul{{list-style:none;font-size:29px;line-height:1.45}} li{{margin-bottom:18px;padding-left:34px;position:relative}} li:before{{content:'';position:absolute;left:0;top:14px;width:16px;height:16px;border-radius:4px;background:#2F7D5B}}
ul.wide{{margin:36px 70px 0;columns:2;column-gap:60px}}
.foot{{position:absolute;left:70px;right:70px;bottom:40px;display:flex;justify-content:space-between;font-size:22px;color:#7A858F}}
</style><h1>{escape(title)}</h1><div class='sub'>{escape(sub)}</div>
{body}
<div class='foot'><span>Real output &middot; {escape(data_note)}</span><span>Built and tested with Claude (AI) &middot; reviewed by me</span></div>"""
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "cover.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={Path(tmp) / 'p'}",
                        "--force-device-scale-factor=1", "--window-size=1600,1200", "--allow-file-access-from-files",
                        f"--screenshot={Path(out).resolve()}", page.as_uri()], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    print("cover", out)


if __name__ == "__main__":
    main(*sys.argv[1:])
