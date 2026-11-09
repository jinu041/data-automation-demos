# Checks the values Excel calculated (run after recalculating in Excel) against expected.json from build.py.
# Run: uv run --no-project --with openpyxl python check.py
import json
from pathlib import Path

from openpyxl import load_workbook

HERE = Path(__file__).parent
exp = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))
ERR = ("#VALUE!", "#REF!", "#NAME?", "#DIV/0!", "#N/A", "#NUM!", "#NULL!")

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
