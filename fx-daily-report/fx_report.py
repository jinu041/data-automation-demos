# Daily exchange-rate report: public API -> Excel (rates table, summary formulas, index chart).
# Data: European Central Bank reference rates via the free Frankfurter API (no key needed).
# Run:       uv run --with openpyxl python fx_report.py -o fx-report.xlsx            (last 30 days, live)
#            uv run --with openpyxl python fx_report.py --offline sample/rates.json -o fx-report.xlsx
# Self-test: uv run --with openpyxl python fx_report.py --selftest
import argparse
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

API = "https://api.frankfurter.dev/v1/{start}..{end}?from={base}&to={to}"
DEC = {"JPY": 2, "KRW": 2}  # other currencies get 4 decimals


def fetch(base, to, days, retries=3):
    end = dt.date.today()
    url = API.format(start=end - dt.timedelta(days=days), end=end, base=base, to=",".join(to))
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fx-report-demo/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except OSError as e:  # network errors and HTTP errors
            if attempt == retries - 1:
                sys.exit(f"Could not fetch rates: {e}")
            time.sleep(2 * (attempt + 1))


def table(data):
    """API JSON -> (currencies, [(date, [rate, ...]), ...]) sorted by date. Missing rates stay None."""
    cur = sorted({c for day in data["rates"].values() for c in day})
    rows = [(dt.date.fromisoformat(d), [data["rates"][d].get(c) for c in cur]) for d in sorted(data["rates"])]
    if not rows:
        sys.exit("The API returned no rates for that period.")
    return cur, rows


def write(data, out):
    from openpyxl import Workbook
    from openpyxl.chart import LineChart, Reference
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter as L

    cur, rows = table(data)
    n = len(rows) + 1  # last data row
    first = [next(i for i, (_, vals) in enumerate(rows, 2) if vals[j] is not None) for j in range(len(cur))]
    baseline = [rows[i - 2][1][j] for j, i in enumerate(first)]
    head = PatternFill("solid", start_color="2F4858", end_color="2F4858")
    wb = Workbook()
    summ = wb.active
    summ.title = "Summary"
    rates, index = wb.create_sheet("Rates"), wb.create_sheet("Index")

    for ws in (rates, index):
        ws.append(["Date"] + cur)
        for c in ws[1]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), head
        ws.column_dimensions["A"].width = 12
        ws.freeze_panes = "B2"
    for i, (d, vals) in enumerate(rows, 2):
        rates.append([d] + vals)
        index.append([d] + [f'=IF(Rates!{L(j)}{i}="","",Rates!{L(j)}{i}/Rates!{L(j)}${first[j - 2]}*100)' for j in range(2, len(cur) + 2)])
        for ws in (rates, index):
            ws[f"A{i}"].number_format = "yyyy-mm-dd"
        for j, c in enumerate(cur, 2):
            rates.cell(i, j).number_format = "#,##0." + "0" * DEC.get(c, 4)
            index.cell(i, j).number_format = "0.0"

    summ["A1"] = f"Exchange rates: 1 {data['base']} in other currencies"
    summ["A1"].font = Font(bold=True, size=14, color="2F4858")
    summ["A2"] = f"{rows[0][0]} to {rows[-1][0]}, {len(rows)} ECB business days. Source: Frankfurter API"
    summ["A2"].font = Font(color="667085")
    summ.append([])
    summ.append(["Currency", "Latest", "Average", "Low", "High", "Change"])
    for c in summ[4]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), head
    for k, c in enumerate(cur, 5):
        col = f"Rates!${L(k - 3)}$2:${L(k - 3)}${n}"
        summ.append([c, f"=LOOKUP(2,1/({col}<>\"\"),{col})", f"=AVERAGE({col})", f"=MIN({col})", f"=MAX({col})",
                     f"=B{k}/Rates!${L(k - 3)}${first[k - 5]}-1"])
        for ref in "BCDE":
            summ[f"{ref}{k}"].number_format = "#,##0." + "0" * DEC.get(c, 4)
        summ[f"F{k}"].number_format = "+0.0%;-0.0%;0.0%"
    for col, w in zip("ABCDEF", (12, 12, 12, 12, 12, 10)):
        summ.column_dimensions[col].width = w

    chart = LineChart()
    chart.title, chart.height, chart.width = "Index (first available rate = 100)", 8, 18
    chart.add_data(Reference(index, min_col=2, max_col=len(cur) + 1, min_row=1, max_row=n), titles_from_data=True)
    chart.set_categories(Reference(index, min_col=1, min_row=2, max_row=n))
    for s in chart.series:
        s.smooth = False  # straight lines between days, no invented curves
    # Show both axes (Excel hides them unless delete is explicitly False) and fit the scale to the data
    idx = [v / baseline[j] * 100 for j in range(len(cur)) for _, r in rows for v in [r[j]] if v is not None and baseline[j]]
    chart.x_axis.delete = chart.y_axis.delete = False
    chart.x_axis.number_format, chart.y_axis.number_format = "mm-dd", "0"
    chart.y_axis.scaling.min, chart.y_axis.scaling.max = int(min(idx)) - 1, int(max(idx)) + 2
    chart.legend.position, chart.legend.overlay = "r", False  # beside the plot, not on top of the lines
    chart.x_axis.tickLblSkip = 4  # one date label every 4 business days
    summ.add_chart(chart, f"A{len(cur) + 7}")

    wb.properties.creator = ""
    wb.save(out)
    return cur, rows


def expected(cur, rows):
    """Summary numbers computed in Python, to compare with what Excel calculates from the formulas."""
    out = {}
    for j, c in enumerate(cur):
        vals = [v[j] for _, v in rows if v[j] is not None]
        out[c] = {"latest": vals[-1], "average": sum(vals) / len(vals), "low": min(vals), "high": max(vals),
                  "change": vals[-1] / vals[0] - 1}
    return out


def selftest():
    import tempfile

    here = Path(__file__).parent
    data = json.loads((here / "sample" / "rates.json").read_text(encoding="utf-8"))
    out = Path(tempfile.mkdtemp()) / "fx.xlsx"
    cur, rows = write(data, out)
    assert cur == sorted(cur) and len(rows) == len(data["rates"]), (cur, len(rows))
    assert all(a[0] < b[0] for a, b in zip(rows, rows[1:])), "dates must be sorted"
    from openpyxl import load_workbook
    wb = load_workbook(out)
    assert wb.sheetnames == ["Summary", "Rates", "Index"] and wb["Rates"].max_row == len(rows) + 1
    assert wb["Summary"]._charts, "chart missing"
    exp = expected(cur, rows)
    assert all(e["low"] <= e["average"] <= e["high"] for e in exp.values())
    missing = {"base": "USD", "rates": {
        "2026-11-02": {"EUR": 1}, "2026-11-03": {"EUR": 1.1, "GBP": 2},
        "2026-11-04": {"EUR": 1.2, "GBP": 3, "JPY": 100}, "2026-11-05": {"JPY": 50}}}
    cur_missing, rows_missing = write(missing, out.parent / "missing.xlsx")
    wb_missing = load_workbook(out.parent / "missing.xlsx")
    for j, (col, start) in enumerate((("B", 2), ("C", 3), ("D", 4)), 5):
        for i in range(2, 6):
            assert wb_missing["Index"][f"{col}{i}"].value == f'=IF(Rates!{col}{i}="","",Rates!{col}{i}/Rates!{col}${start}*100)'
        assert wb_missing["Summary"][f"F{j}"].value == f"=B{j}/Rates!${col}${start}-1"
        assert wb_missing["Rates"][f"{col}{start}"].value is not None
    changes = expected(cur_missing, rows_missing)
    assert changes["GBP"]["change"] == 0.5 and changes["JPY"]["change"] == -0.5
    scale = wb_missing["Summary"]._charts[0].y_axis.scaling
    assert scale.min == 49 and scale.max == 152, (scale.min, scale.max)
    print("selftest ok:", out, {c: round(e["change"] * 100, 2) for c, e in exp.items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="USD")
    ap.add_argument("--to", default="EUR,GBP,JPY,KRW")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--offline", type=Path, help="read rates from a saved JSON instead of the API")
    ap.add_argument("-o", "--out", type=Path, default=Path("fx-report.xlsx"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        sys.exit()
    data = json.loads(a.offline.read_text(encoding="utf-8")) if a.offline else fetch(a.base, a.to.split(","), a.days)
    cur, rows = write(data, a.out)
    print(f"{len(rows)} days, {', '.join(cur)} -> {a.out}")
