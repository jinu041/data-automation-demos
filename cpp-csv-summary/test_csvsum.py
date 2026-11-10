# Builds csvsum with g++ and checks it against totals computed independently with Python's csv module.
# Run: python test_csvsum.py   (needs g++ on PATH)
import csv
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
EXE = Path(tempfile.mkdtemp()) / ("csvsum.exe" if os.name == "nt" else "csvsum")
# -static on Windows: another program's libstdc++-6.dll earlier on PATH (Git ships one) can otherwise be loaded instead
# of the compiler's own and break stream error checks.
STATIC = ["-static"] if os.name == "nt" else []
subprocess.run(["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", *STATIC, "-o", str(EXE), str(HERE / "csvsum.cpp")],
               check=True)


def run(*args):
    return subprocess.run([str(EXE), *map(str, args)], capture_output=True, text=True)


def number(s):
    s = s.replace(" ", "").replace(",", "").replace("$", "")
    neg = len(s) > 2 and s[0] == "(" and s[-1] == ")"
    s = s[1:-1] if neg else s
    v = float(s)  # raises ValueError for 'N/A'
    return -v if neg else v


def expected(path, group, col):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    head = rows[0]
    gi, si = head.index(group), head.index(col)
    out, bad = defaultdict(list), 0
    for r in rows[1:]:
        try:
            assert len(r) == len(head)
            out[r[gi].strip()].append(number(r[si]))
        except (AssertionError, ValueError):
            bad += 1
    return out, bad


# 1. Sample file: compare every group with the Python totals
sample = HERE / "sample" / "sales.csv"
out_csv = EXE.parent / "summary.csv"
r = run(sample, "--group", "Region", "--sum", "Amount", "--out", out_csv)
assert r.returncode == 0, r.stderr
exp, bad = expected(sample, "Region", "Amount")
with open(out_csv, newline="") as f:
    got = {row["Region"]: row for row in csv.DictReader(f)}
assert set(got) == set(exp), (got.keys(), exp.keys())
for g, vals in exp.items():
    row = got[g]
    assert int(row["Rows"]) == len(vals)
    assert abs(float(row["Total"]) - round(sum(vals), 2)) < 0.005, (g, row["Total"], sum(vals))
    assert abs(float(row["Min"]) - min(vals)) < 0.005 and abs(float(row["Max"]) - max(vals)) < 0.005
totals = [float(v["Total"]) for v in got.values()]
assert totals == sorted(totals, reverse=True), "groups must be sorted by total"
assert "2 row(s) skipped" in r.stderr and bad == 2
assert re.search(r"line 11: Amount is not a number \('N/A'\)", r.stderr), r.stderr
assert re.search(r"line 17: 4 fields, header has 6", r.stderr), r.stderr
grand = sum(sum(v) for v in exp.values())
assert re.search(r"TOTAL\s+14\s+%.2f" % grand, r.stdout), r.stdout

# 2. Grouping by a column whose values contain commas, quotes and a line break
r = run(sample, "--group", "Store", "--sum", "Amount", "--out", out_csv)
with open(out_csv, newline="") as f:
    stores = {row["Store"]: float(row["Total"]) for row in csv.DictReader(f)}
assert stores["Smith, Jones & Co"] == 990.0 and stores['The "Corner" Shop'] == 99.8 and stores["Market\nHall"] == 60.0, stores

# 3. Errors: unknown column, missing file, empty file
r = run(sample, "--group", "Country", "--sum", "Amount")
assert r.returncode == 1 and "no column named 'Country'" in r.stderr and "[Region]" in r.stderr
assert run(HERE / "missing.csv", "--group", "A", "--sum", "B").returncode == 1
empty = EXE.parent / "empty.csv"
empty.write_text("")
r = run(empty, "--group", "A", "--sum", "B")
assert r.returncode == 1 and "is empty" in r.stderr

# 4. Quotes must enclose a whole field; malformed rows cannot change totals.
quoted = EXE.parent / "quoted.csv"
quoted.write_text(
    'Region,Amount\n'
    'North,1"2"\n'
    'North,"1"2\n'
    '"No"rth,12\n'
    '"North",12\n'
    '"The ""Corner"" Shop",3\n'
    '"Market\nHall",4\n'
    '"Smith, Jones & Co","1,200.00"\n'
    '"bad"x,99\n'
    '"bad",99"x"\n',
    encoding="utf-8",
)
r = run(quoted, "--group", "Region", "--sum", "Amount", "--out", out_csv)
assert r.returncode == 0, r.stderr
assert "5 row(s) skipped" in r.stderr, r.stderr
for line in (2, 3, 4, 10, 11):
    assert f"line {line}: malformed CSV quoting" in r.stderr, r.stderr
with open(out_csv, newline="") as f:
    got = {row["Region"]: float(row["Total"]) for row in csv.DictReader(f)}
assert got == {"North": 12, 'The "Corner" Shop': 3, f"Market{os.linesep}Hall": 4, "Smith, Jones & Co": 1200}, got
quoted.write_text('Re"gion",Amount\nNorth,1\n', encoding="utf-8")
r = run(quoted, "--group", "Region", "--sum", "Amount")
assert r.returncode == 1 and "line 1: malformed CSV quoting" in r.stderr, r.stderr
quoted.write_text('Region,Amount\nNorth,1\n"never closed,99\n', encoding="utf-8")
r = run(quoted, "--group", "Region", "--sum", "Amount")
assert r.returncode == 0 and "line 3: quote is never closed" in r.stderr, r.stderr
assert "1 row(s) skipped" in r.stderr and re.search(r"TOTAL\s+1\s+1.00", r.stdout), r.stdout

# 5. Failed output creation must not claim success.
for target in (EXE.parent / "missing" / "summary.csv", EXE.parent):
    r = run(sample, "--group", "Region", "--sum", "Amount", "--out", target)
    assert r.returncode == 1 and f"error: cannot open {target}" in r.stderr, (target, r.returncode, r.stdout, r.stderr)
    assert "summary written to" not in r.stdout, r.stdout

# /dev/full rejects writes; small output fails on buffered close, large output on write.
if os.name != "nt" and Path("/dev/full").exists():
    for count, operation in ((1, "close"), (2000, "write")):
        quoted.write_text("Region,Amount\n" + "".join(f"Group{i},1\n" for i in range(count)), encoding="utf-8")
        r = run(quoted, "--group", "Region", "--sum", "Amount", "--out", "/dev/full")
        assert r.returncode == 1 and f"error: cannot {operation} /dev/full" in r.stderr, r.stderr
        assert "summary written to" not in r.stdout, r.stdout
else:
    print("skipped buffered close/write failure checks: /dev/full unavailable")

print("all tests passed")
print(run(sample, "--group", "Region", "--sum", "Amount").stdout, end="")
