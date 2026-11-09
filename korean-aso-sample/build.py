# Korean App Store / Google Play listing sample for a fictional vocabulary app.
# Checks every field against the store limits and the "no keyword repeats" rule, then writes the cover image.
# Run: python build.py
import subprocess
import tempfile
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

APP = {  # (Korean, English back-translation)
    "ios_title": ("워드온: 토익·수능 영단어 암기", "WordOn: TOEIC & SAT-style English vocabulary memorizing"),
    "ios_subtitle": ("하루 10분 단어장, 발음과 퀴즈로 복습", "10-minute daily word book, review with pronunciation and quizzes"),
    "ios_keywords": ("영어단어,보카,어휘,숙어,중학영어,고등영어,영어공부,외우기,스펠링,예문,편입,공무원,TOEIC",
                     "English words, voca, vocabulary, idioms, middle-school English, high-school English, English study, "
                     "memorize, spelling, example sentences, transfer exam, civil-service exam, TOEIC"),
    "gp_title": ("워드온 - 토익·수능 영단어 암기 단어장", "WordOn - TOEIC & SAT-style vocabulary word book"),
    "gp_short": ("하루 10분, 토익·수능 필수 영단어를 발음과 예문, 퀴즈로 외우는 단어장 앱",
                 "10 minutes a day: learn must-know TOEIC and SAT-style words with pronunciation, example sentences and quizzes"),
}
LIMITS = {"ios_title": 30, "ios_subtitle": 30, "ios_keywords": 100, "gp_title": 30, "gp_short": 80}


def checks():
    out = {}
    for k, (ko, _) in APP.items():
        assert len(ko) <= LIMITS[k], (k, len(ko))
        out[k] = len(ko)
    kw = APP["ios_keywords"][0].split(",")
    assert " " not in APP["ios_keywords"][0], "no spaces in the keyword field"
    assert len(kw) == len(set(kw)), "duplicate keyword"
    indexed = APP["ios_title"][0] + APP["ios_subtitle"][0]
    repeats = [w for w in kw if w in indexed]
    assert not repeats, f"keywords already in title/subtitle: {repeats}"
    return out


def cover(counts):
    ko = {k: escape(v[0]) for k, v in APP.items()}
    chips = "".join(f"<span>{escape(w)}</span>" for w in APP["ios_keywords"][0].split(","))
    html = f"""<!doctype html><meta charset='utf-8'><style>
*{{margin:0;padding:0;box-sizing:border-box}} body{{width:1600px;height:1200px;overflow:hidden;background:#F4F1EC;font-family:'Segoe UI','Malgun Gothic',sans-serif;color:#1F2A33}}
h1{{font-size:62px;font-weight:800;letter-spacing:-1px;margin:64px 70px 0}} .sub{{font-size:30px;color:#5B6670;margin:14px 70px 0}}
.wrap{{display:flex;gap:40px;margin:44px 70px 0}} .card{{flex:1;background:#fff;border:2px solid #CDD5DC;border-radius:22px;padding:34px 36px;box-shadow:0 10px 26px rgba(31,42,51,.12)}}
.lab{{font-size:20px;font-weight:700;color:#7A858F;letter-spacing:1px;margin-top:22px}} .lab:first-child{{margin-top:0}}
.v{{font-family:'Malgun Gothic',sans-serif;font-size:31px;font-weight:700;margin-top:8px;line-height:1.35}} .v.s{{font-size:26px;font-weight:400}}
.n{{font-size:20px;color:#2F7D5B;font-weight:700;margin-top:6px}} .chips{{display:flex;flex-wrap:wrap;gap:9px;margin-top:10px}}
.chips span{{font-family:'Malgun Gothic',sans-serif;background:#1F2A33;color:#F4F1EC;border-radius:999px;padding:6px 14px;font-size:21px}}
.foot{{position:absolute;left:70px;right:70px;bottom:40px;display:flex;justify-content:space-between;font-size:22px;color:#7A858F}}
</style><h1>Korean App Store &amp; Google Play listing</h1><div class='sub'>Sample for a fictional app · every field within the store limits · English back-translation included</div>
<div class='wrap'><div class='card'><div class='lab'>APP STORE · TITLE</div><div class='v'>{ko['ios_title']}</div><div class='n'>{counts['ios_title']} / 30</div>
<div class='lab'>SUBTITLE</div><div class='v'>{ko['ios_subtitle']}</div><div class='n'>{counts['ios_subtitle']} / 30</div>
<div class='lab'>KEYWORD FIELD</div><div class='chips'>{chips}</div><div class='n'>{counts['ios_keywords']} / 100 · no spaces · nothing repeated from the title or subtitle</div></div>
<div class='card'><div class='lab'>GOOGLE PLAY · TITLE</div><div class='v'>{ko['gp_title']}</div><div class='n'>{counts['gp_title']} / 30</div>
<div class='lab'>SHORT DESCRIPTION</div><div class='v s'>{ko['gp_short']}</div><div class='n'>{counts['gp_short']} / 80</div></div></div>
<div class='foot'><span>Sample with a fictional app</span><span>Drafted with Claude (AI) · Korean read by a native speaker</span></div>"""
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "c.html"
        page.write_text(html, encoding="utf-8")
        (HERE / "screenshots").mkdir(exist_ok=True)
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={Path(tmp) / 'p'}",
                        "--force-device-scale-factor=1", "--window-size=1600,1200", f"--screenshot={HERE / 'screenshots' / 'cover.png'}",
                        page.as_uri()], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


if __name__ == "__main__":
    counts = checks()
    cover(counts)
    print("ok", counts)
