# Checks the values Excel calculated (run after recalculating in Excel) against expected.json from build.py.
# Run: uv run --no-project --with openpyxl python check.py
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote

from openpyxl import load_workbook

HERE = Path(__file__).parent
ERR = ("#VALUE!", "#REF!", "#NAME?", "#DIV/0!", "#N/A", "#NUM!", "#NULL!")


def selftest():
    from build import SOURCES, build

    out = io.BytesIO()
    build(out, [])
    wb = load_workbook(out)
    dash = wb["Dashboard"]
    for i in range(12, 12 + len(SOURCES)):
        assert dash[f"D{i}"].value == f"=Lists!A{i - 10}"
        assert dash[f"E{i}"].value == f'=COUNTIF(Leads!$F$2:$F$501,D{i})'
        assert dash[f"F{i}"].value == f'=COUNTIFS(Leads!$F$2:$F$501,D{i},Leads!$I$2:$I$501,"Won")'
    wb["Lists"]["A2"] = "New source + 50%"
    assert wb["Lists"][dash["D12"].value.split("!")[1]].value == "New source + 50%"
    for row in (2, 501):
        formula = wb["Leads"][f"M{row}"].value
        assert f'C{row}&IF(D{row}=""," "," - "&D{row})' in formula
        replacements = re.findall(r',"([^"]*)","([^"]*)"\)', formula)
        for name, company in (("A+B 50% off", "R&D #1"), ("100%20 + %2B", "")):
            text = "Follow up: " + name + (" - " + company if company else " ")
            encoded = text
            for old, new in replacements:
                encoded = encoded.replace(old, new)
            assert encoded == quote(text, safe=":"), (encoded, text)
            assert parse_qs("text=" + encoded)["text"] == [text]
    print("selftest ok: source label references, calendar +/% round-trip")


if __name__ == "__main__" and "--selftest" in sys.argv:
    selftest()
    sys.exit()

exp = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))
for name in ("lead-tracker.xlsx", "lead-tracker-sample.xlsx"):
    wb = load_workbook(HERE / name, data_only=True)
    errs = [f"{ws.title}!{c.coordinate}={c.value}" for ws in wb for row in ws.iter_rows() for c in row
            if isinstance(c.value, str) and c.value.startswith(ERR)]
    assert not errs, errs[:10]
    d = wb["Dashboard"]
    got = {k: d[f"B{i}"].value for i, k in enumerate(["total", "new_this_month", "open_value", "won_value", "win_rate", "overdue", "this_week"], 4)}
    if name == "lead-tracker.xlsx":
        assert got["total"] == 0 and got["open_value"] == 0 and got["win_rate"] in ("", None), got
    else:
        for k, v in got.items():
            assert abs(float(v) - exp[k]) < 1e-9, (k, v, exp[k])
        leads = wb["Leads"]
        assert leads["A2"].value == "L-001" and leads["A14"].value in ("", None)
        assert sum(1 for r in range(2, 14) if leads[f"L{r}"].value == "Overdue") == exp["overdue"]
    print(name, "ok", got)
