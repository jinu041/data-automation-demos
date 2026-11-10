"""Clean a messy sales sheet into one flat table you can sort, filter and pivot.

Merged cells are filled in, every date becomes a real date, first and last names are joined, and subtotal rows,
repeated header rows, blank rows and exact duplicates are removed. Anything it can't decide for sure (a date that
reads two ways, an amount like "n/a", two rows that are almost the same) goes on a Check sheet instead of being
guessed. Every change is listed on a Log sheet, and a Monthly Summary uses live formulas."""
import argparse
import datetime as dt
import random
import re
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

HEAD = ["Date", "Customer", "Region", "Product", "Qty", "Amount", "Source row"]
ALIASES = {  # header text in the messy sheet (lower case) -> field
    "date": "Date", "order date": "Date", "sale date": "Date",
    "first name": "First", "first": "First", "last name": "Last", "last": "Last", "surname": "Last",
    "customer": "Customer", "customer name": "Customer", "client": "Customer", "name": "Customer",
    "region": "Region", "area": "Region", "territory": "Region",
    "product": "Product", "item": "Product",
    "qty": "Qty", "quantity": "Qty", "units": "Qty",
    "amount": "Amount", "amount ($)": "Amount", "sales": "Amount", "total": "Amount", "revenue": "Amount",
}
MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
MONTHS = {m.lower(): i for i, m in enumerate(MON, 1)}
SLASH = re.compile(r"(\d{1,2})([/.-])(\d{1,2})\2(\d{4}|\d{2})")
TOTAL = re.compile(r"(?i)\b(sub)?total\b")
HFONT, HFILL = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E78")
YELLOW = PatternFill("solid", fgColor="FFF2CC")


def norm(v):
    return re.sub(r"\s+", " ", str(v)).strip().lower() if v is not None else ""


def text(v):
    return "" if v is None else str(v)


def fmt(d):
    return f"{d.day} {MON[d.month - 1]} {d.year}"


def parse_date(v):
    """(date, None) when the value can mean only one day, (None, (sep, a, b, year)) for a/b/yyyy where a and b are
    both 12 or less, (None, None) when it isn't a date."""
    if isinstance(v, dt.datetime):
        return v.date(), None
    if isinstance(v, dt.date):
        return v, None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(v)), None) if 20000 < v < 80000 else (None, None)
    s = re.sub(r"\s+", " ", text(v)).strip()
    try:
        if m := re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s):
            return dt.date(*map(int, m.groups())), None
        if m := SLASH.fullmatch(s):
            a, sep, b, y = int(m[1]), m[2], int(m[3]), int(m[4])
            y += 2000 if y < 100 else 0
            if a > 12:  # only day/month works
                return dt.date(y, b, a), None
            if b > 12 or a == b:  # only month/day works, or both readings are the same day
                return dt.date(y, a, b), None
            return None, (sep, a, b, y)
        if m := re.fullmatch(r"([A-Za-z]{3})[a-z]*\.? (\d{1,2}),? (\d{4})", s):  # Sep 3, 2026
            return dt.date(int(m[3]), MONTHS[m[1].lower()], int(m[2])), None
        if m := re.fullmatch(r"(\d{1,2})[ -]([A-Za-z]{3})[a-z]*\.?[ -](\d{4})", s):  # 3 Sep 2026, 03-Sep-2026
            return dt.date(int(m[3]), MONTHS[m[2].lower()], int(m[1])), None
    except (KeyError, ValueError):
        pass
    return None, None


def conventions(values):
    """{separator: 'md' or 'dm'} for each separator whose one-way dates (like 09/17/2026) all agree."""
    seen = {}
    for v in values:
        if isinstance(v, str) and (m := SLASH.fullmatch(v.strip())) and (int(m[1]) > 12) != (int(m[3]) > 12):
            seen.setdefault(m[2], set()).add("dm" if int(m[1]) > 12 else "md")
    return {sep: next(iter(ways)) for sep, ways in seen.items() if len(ways) == 1}


def parse_amount(v):
    """Numbers, '$1,250.00', 'USD 30', '(24.50)' or '-24.50' for a refund. Anything else ('n/a', '12k') is None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = text(v).strip()
    neg = (s.startswith("(") and s.endswith(")")) or s.startswith("-")
    core = re.sub(r"(?i)usd|[$,\s()]|^-", "", s)
    return round(-float(core) if neg else float(core), 2) if re.fullmatch(r"\d+(\.\d+)?", core) else None


def parse_qty(v):
    try:
        q = float(text(v).replace(",", "").strip())
    except ValueError:
        return None
    return int(q) if q.is_integer() and q != 0 else None


def clean_name(*cells):
    """'  anna ', 'SMITH' -> 'Anna Smith'. A cell typed in mixed case (McDonald, van der Berg) is left as typed."""
    parts = [re.sub(r"\s+", " ", text(c)).strip() for c in cells]
    return " ".join(p.title() if p.isupper() or p.islower() else p for p in parts if p)


def read_grid(path, sheet=None):
    """Cell values of one sheet with every merged range filled in, and {(row, col): 'D4:D13'} for the filled cells."""
    wb = load_workbook(path, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    grid = [list(r) for r in ws.iter_rows(values_only=True)]
    filled = {}
    for rng in ws.merged_cells.ranges:
        v = grid[rng.min_row - 1][rng.min_col - 1]
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                if (r, c) != (rng.min_row, rng.min_col):
                    grid[r - 1][c - 1], filled[(r, c)] = v, rng.coord
    return grid, filled


def find_header(grid):
    """Row index and {field: column} of the first row (within the first 10) that names at least 3 known columns."""
    for i, row in enumerate(grid[:10]):
        cols = {}
        for j, v in enumerate(row):
            if (f := ALIASES.get(norm(v))) and f not in cols:
                cols[f] = j
        if len(cols) >= 3:
            return i, cols
    return None, {}


def clean(grid, filled):
    """Returns (rows, checks, log). rows: dicts keyed by HEAD plus '_check' (columns to highlight);
    checks: (source row, column, value as typed, why); log: (source row, what happened)."""
    h, cols = find_header(grid)
    if h is None or not {"Date", "Amount"} <= cols.keys() or not {"Customer", "First"} & cols.keys():
        sys.exit("no header row with Date, Amount and a name column in the first 10 rows")
    header = [norm(v) for v in grid[h]]
    names = ["Customer"] if "Customer" in cols else ["First", "Last"]
    conv = conventions(row[cols["Date"]] for row in grid[h + 1:])
    rows, checks, log, seen, near = [], [], [], {}, {}
    for r, row in enumerate(grid[h + 1:], start=h + 2):
        get = lambda f: row[cols[f]] if f in cols else None  # noqa: E731
        cells = [v for v in row if text(v).strip()]
        if not cells:
            log.append((r, "removed: blank row"))
            continue
        if [norm(v) for v in row] == header:
            log.append((r, "removed: repeated header row"))
            continue
        raw_date = get("Date")
        date, two_ways = parse_date(raw_date)
        if date is None and any(isinstance(v, str) and TOTAL.search(v) for v in cells):
            log.append((r, "removed: subtotal or total row"))
            continue
        todo, fixes = [], [f"{f} filled from merged cells {filled[(r, j + 1)]}"
                           for f, j in cols.items() if (r, j + 1) in filled]
        if two_ways:
            sep, a, b, y = two_ways
            if way := conv.get(sep):
                date = dt.date(y, a, b) if way == "md" else dt.date(y, b, a)
                fixes.append(f"date '{raw_date}' read as {'month/day' if way == 'md' else 'day/month'}, "
                             f"like the other '{sep}' dates in the sheet")
            else:
                todo.append((r, "Date", raw_date, f"reads two ways: {fmt(dt.date(y, a, b))} or {fmt(dt.date(y, b, a))}"))
        elif date is None:
            todo.append((r, "Date", raw_date, "not a real date"))
        elif isinstance(raw_date, str):
            fixes.append(f"date '{raw_date}' -> {date.isoformat()}")
        elif not isinstance(raw_date, (dt.date, dt.datetime)):
            fixes.append(f"date number {raw_date} (a date that lost its format) -> {date.isoformat()}")
        typed = " ".join(text(v) for v in (get(f) for f in names) if text(v))
        name = clean_name(*(get(f) for f in names))
        if name != typed:
            fixes.append(f"name '{typed}' -> '{name}'")
        if not name:
            todo.append((r, "Customer", "", "no name"))
        region, product = (re.sub(r"\s+", " ", text(get(f))).strip() for f in ("Region", "Product"))
        for f, v in (("Region", region), ("Product", product)):
            if f in cols and v != text(get(f)) and (r, cols[f] + 1) not in filled:
                fixes.append(f"{f.lower()} '{get(f)}' -> '{v}'")
        qty = parse_qty(get("Qty")) if "Qty" in cols else None
        if "Qty" in cols and qty is None:
            todo.append((r, "Qty", get("Qty"), "not a whole number"))
        elif isinstance(get("Qty"), str):
            fixes.append(f"qty '{get('Qty')}' -> {qty}")
        amount = parse_amount(get("Amount"))
        if amount is None:
            todo.append((r, "Amount", get("Amount"), "not an amount"))
        elif isinstance(get("Amount"), str):
            fixes.append(f"amount '{get('Amount')}' -> {amount:.2f}")
        key = (date or text(raw_date), name.lower(), region.lower(), product.lower(), qty, amount)
        if key in seen:
            log.append((r, f"removed: exact duplicate of row {seen[key]}"))
            continue
        seen[key] = r
        if date and (date, name.lower(), product.lower()) in near:
            todo.append((r, "Row", "", f"same customer, date and product as row {near[date, name.lower(), product.lower()]}"
                                       f" but a different qty or amount: keep both?"))
        near.setdefault((date, name.lower(), product.lower()), r)
        checks += todo
        if fixes:
            log.append((r, "; ".join(fixes)))
        rows.append({"Date": date, "Customer": name, "Region": region, "Product": product, "Qty": qty,
                     "Amount": amount, "Source row": r, "_check": {c for _, c, _, _ in todo}})
    rows.sort(key=lambda o: (o["Date"] is None, o["Date"] or dt.date.min, o["Source row"]))
    return rows, checks, log


def keep_text(ws):
    """Typed text that starts with '=' stays text. openpyxl would otherwise save it as a live formula."""
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                c.data_type = "s"


def head_row(ws, row, widths):
    for c in ws[row]:
        c.font, c.fill = HFONT, HFILL
    for col, w in zip("ABCDEFG", widths):
        ws.column_dimensions[col].width = w


def write_xlsx(rows, checks, log, path, source):
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(HEAD)
    for k, o in enumerate(rows, start=2):
        ws.append([o[c] for c in HEAD])
        for c in o["_check"]:
            for cell in (ws[k] if c == "Row" else [ws.cell(k, HEAD.index(c) + 1)]):
                cell.fill = YELLOW
    keep_text(ws)
    n = max(len(rows) + 1, 2)
    for r in range(2, n + 1):
        ws[f"A{r}"].number_format, ws[f"F{r}"].number_format = "yyyy-mm-dd", "#,##0.00"
    head_row(ws, 1, (12, 20, 10, 22, 6, 11, 11))
    ws.freeze_panes, ws.auto_filter.ref = "A2", f"A1:G{n}"

    sm = wb.create_sheet("Monthly Summary")
    sm["A1"], sm["A1"].font = "Sales by month", Font(bold=True, size=13)
    sm["A2"] = f"From {source}, cleaned {dt.date.today().isoformat()}. The formulas read the Sales sheet."
    for col, t in zip("ABCD", ("Month", "Orders", "Units", "Amount")):
        sm[f"{col}4"] = t
    head_row(sm, 4, (24, 9, 9, 13))
    d, q, a = (f"Sales!{c}2:{c}{n}" for c in "AEF")
    months = sorted({o["Date"].replace(day=1) for o in rows if o["Date"]})
    for k, m in enumerate(months, start=5):
        crit = f'{d},">="&A{k},{d},"<"&EDATE(A{k},1)'
        sm[f"A{k}"], sm[f"A{k}"].number_format = m, "mmm yyyy"
        sm[f"B{k}"], sm[f"C{k}"], sm[f"D{k}"] = f"=COUNTIFS({crit})", f"=SUMIFS({q},{crit})", f"=SUMIFS({a},{crit})"
    k = 5 + len(months)
    sm[f"A{k}"], sm[f"B{k}"] = "No date yet (see Check)", f'=COUNTIFS({d},"")'
    sm[f"C{k}"], sm[f"D{k}"] = f'=SUMIFS({q},{d},"")', f'=SUMIFS({a},{d},"")'
    sm[f"A{k + 1}"], sm[f"B{k + 1}"] = "Total", f"=COUNT(Sales!G2:G{n})"
    sm[f"C{k + 1}"], sm[f"D{k + 1}"] = f"=SUM({q})", f"=SUM({a})"
    for col in "ABCD":
        sm[f"{col}{k + 1}"].font = Font(bold=True)
    for r in range(5, k + 2):
        sm[f"D{r}"].number_format = "#,##0.00"
    sm[f"A{k + 3}"] = f"Cells to check: {len(checks)} (Check sheet). Rows removed or changed: Log sheet."

    for title, head, lines, widths in (("Check", ["Source row", "Column", "As typed", "Why"], checks, (11, 10, 16, 80)),
                                       ("Log", ["Source row", "What happened"], log, (11, 110))):
        sh = wb.create_sheet(title)
        sh.append(head)
        for line in lines:
            sh.append([text(v) if i == 2 else v for i, v in enumerate(line)])
        keep_text(sh)
        head_row(sh, 1, widths)
        sh.freeze_panes = "A2"
    wb.save(path)


def stats(sel):
    return len(sel), sum(o["Qty"] or 0 for o in sel), round(sum(o["Amount"] or 0 for o in sel), 2)


def expected(rows):
    """Monthly Summary cells and the values Python computes for them from the rows."""
    months = sorted({o["Date"].replace(day=1) for o in rows if o["Date"]})
    groups = [[o for o in rows if o["Date"] and o["Date"].replace(day=1) == m] for m in months]
    groups += [[o for o in rows if not o["Date"]], rows]
    return {f"{col}{k}": v for k, sel in enumerate(groups, start=5) for col, v in zip("BCD", stats(sel))}


def check(path):
    """After Excel has recalculated the file: every Monthly Summary value must match Python's own numbers."""
    wb = load_workbook(path, data_only=True)
    rows = [dict(zip(HEAD, (r[0].date() if isinstance(r[0], dt.datetime) else r[0], *r[1:7])))
            for r in wb["Sales"].iter_rows(min_row=2, values_only=True) if r[6] is not None]
    for cell, want in expected(rows).items():
        got = wb["Monthly Summary"][cell].value
        assert got is not None, f"{cell} has no cached value: open and save the file in Excel first"
        assert abs(float(got) - want) < 1e-6, (cell, got, want)
    print(f"check ok: {len(rows)} rows, every Monthly Summary value matches Python")


FIRST = ["Anna", "Ben", "Chloe", "David", "Emma", "Felix", "Grace", "Hugo", "Iris", "Jack"]
LAST = ["Smith", "Carter", "Nguyen", "Lopez", "Brown", "Novak", "Kim", "Silva", "Meyer", "Okafor"]
PRICES = {"Espresso beans 1kg": 24.5, "Paper cups (1000)": 39.0, "Oat milk case": 18.75, "Grinder cleaning kit": 12.0}
HEADER_IN = ["Date", "First Name", "Last Name", "Region", "Product", "Qty", "Amount"]


def make_sample(path):
    """A made-up messy sheet, and what cleaning it must give: (clean rows, removed rows, cells to check).
    30 sales typed with the usual problems: a merged title, Region merged down two blocks, dates typed six ways
    (plus one that reads two ways and one that can't exist), names in two columns with stray caps and spaces,
    amounts as text, a refund in brackets, 'n/a', '2 boxes', subtotal rows, a repeated header, a blank row, two
    rows pasted twice and a corrected entry typed under the original."""
    rnd = random.Random(11)
    recs = []
    for i in range(30):
        p, q = rnd.choice(sorted(PRICES)), rnd.randint(1, 6)
        recs.append({"Date": dt.date(2026, 9, 1) + dt.timedelta(days=2 * i), "First": FIRST[i % 10],
                     "Last": LAST[i * 3 % 10], "Region": ("North", "South", "West")[i // 10], "Product": p,
                     "Qty": q, "Amount": round(PRICES[p] * q, 2)})
    recs[9].update(Product="Espresso beans 1kg", Qty=1, Amount=-24.5)  # a refund
    recs[11]["Last"] = ""  # no last name
    fix = dict(recs[25], Qty=recs[25]["Qty"] + 1, Amount=round(PRICES[recs[25]["Product"]] * (recs[25]["Qty"] + 1), 2))

    def typed(i, rec):
        d = rec["Date"]
        date = [d, d.isoformat(), f"{d.month:02d}/{d.day:02d}/{d.year}", f"{MON[d.month - 1]} {d.day}, {d.year}",
                fmt(d), (d - dt.date(1899, 12, 30)).days][i % 6]
        date = {16: "03.10.2026", 23: "09/31/2026"}.get(i, date)  # reads two ways / can't exist
        first, last = rec["First"], rec["Last"]
        if i in (3, 17):
            first, last = first.lower(), last.upper()
        if i == 7:
            first, last = f"  {first} ", f"{last}  "
        amt = rec["Amount"]
        amt = "(24.50)" if i == 9 else "n/a" if i == 12 else f"${amt:,.2f}" if i % 4 == 1 else amt
        qty = "2 boxes" if i == 19 else str(rec["Qty"]) if i % 5 == 2 else rec["Qty"]
        region = " West " if rec["Region"] == "West" else rec["Region"]
        return [date, first, last, region, rec["Product"], qty, amt]

    def truth(i, rec, row):
        return {"Date": None if i in (16, 23) else rec["Date"], "Customer": f"{rec['First']} {rec['Last']}".strip(),
                "Region": rec["Region"], "Product": rec["Product"], "Qty": None if i == 19 else rec["Qty"],
                "Amount": None if i == 12 else rec["Amount"], "Source row": row}

    wb = Workbook()
    ws = wb.active
    ws.title = "Sales log"
    out, removed, checks, at = [], [], [], {}
    n = 0

    def put(values):
        nonlocal n
        ws.append(values)
        n += 1
        return n

    put(["Sales log, September to October 2026 (made-up data)"])
    ws.merge_cells("A1:G1")
    put([])
    put(HEADER_IN)
    for block in range(3):
        if block == 1:
            removed.append((put(HEADER_IN), "repeated header"))
        start = n + 1
        for i in range(block * 10, block * 10 + 10):
            vals = typed(i, recs[i])
            if block < 2 and i % 10:
                vals[3] = None  # Region typed once and merged down the block
            at[i] = put(vals)
            out.append(truth(i, recs[i], at[i]))
            if i == 14:  # pasted twice
                removed.append((put(vals), f"exact duplicate of row {at[14]}"))
            if i == 25:  # a corrected entry typed under the original
                out.append(truth(25, fix, put(typed(25, fix)[:5] + [fix["Qty"], fix["Amount"]])))
                checks.append((n, "Row"))
        if block < 2:
            ws.merge_cells(f"D{start}:D{n}")
            sel = recs[block * 10:block * 10 + 10]
            removed.append((put([None] * 4 + [f"{sel[0]['Region']} subtotal", sum(r["Qty"] for r in sel),
                                               round(sum(r["Amount"] for r in sel), 2)]), "subtotal"))
        if block == 1:
            removed.append((put([]), "blank row"))
    removed.append((put(typed(4, recs[4])), f"exact duplicate of row {at[4]}"))
    removed.append((put([None] * 4 + ["Grand total", sum(r["Qty"] for r in recs),
                                      round(sum(r["Amount"] for r in recs), 2)]), "total"))
    checks += [(at[16], "Date"), (at[23], "Date"), (at[12], "Amount"), (at[19], "Qty")]
    for col, w in zip("ABCDEFG", (13, 11, 11, 9, 20, 8, 10)):
        ws.column_dimensions[col].width = w
    wb.save(path)
    return out, removed, sorted(checks)


def selftest():
    assert parse_date("2026-09-03") == (dt.date(2026, 9, 3), None) and parse_date("Sept 3, 2026")[0] == dt.date(2026, 9, 3)
    assert parse_date("03-Sep-2026")[0] == dt.date(2026, 9, 3) and parse_date("09/17/2026")[0] == dt.date(2026, 9, 17)
    assert parse_date("17.09.2026")[0] == dt.date(2026, 9, 17) and parse_date("05/05/26")[0] == dt.date(2026, 5, 5)
    assert parse_date("03/04/2026") == (None, ("/", 3, 4, 2026)) and parse_date("09/31/2026") == (None, None)
    assert parse_date(46280)[0] == dt.date(2026, 9, 15) and parse_date(5) == (None, None)
    assert parse_date("Foo 3, 2026") == (None, None) and parse_date(None) == (None, None) and parse_date(True) == (None, None)
    assert conventions(["09/17/2026", "03/04/2026", "17.09.2026", 3]) == {"/": "md", ".": "dm"}
    assert conventions(["09/17/2026", "17/09/2026"]) == {}
    assert parse_amount("$1,250.00") == 1250.0 and parse_amount("(24.50)") == -24.5 and parse_amount("USD 30") == 30.0
    assert parse_amount("n/a") is None and parse_amount("12k") is None and parse_amount("") is None
    assert parse_qty("3") == 3 and parse_qty(2.0) == 2 and parse_qty("2 boxes") is None and parse_qty("0") is None
    assert clean_name("  anna ", "SMITH") == "Anna Smith" and clean_name("Mia", "") == "Mia"
    assert clean_name("Ian", "McDonald") == "Ian McDonald" and clean_name("o'neil", None) == "O'Neil"
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "messy.xlsx", Path(tmp) / "clean.xlsx"
        truth, removed, want_checks = make_sample(src)
        grid, filled = read_grid(src)
        rows, checks, log = clean(grid, filled)
        got = [{k: v for k, v in o.items() if k != "_check"} for o in rows]
        want = sorted(truth, key=lambda o: (o["Date"] is None, o["Date"] or dt.date.min, o["Source row"]))
        assert got == want, [(g, w) for g, w in zip(got, want) if g != w][:2]
        gone = [(r, what) for r, what in log if what.startswith("removed")]
        assert [r for r, _ in gone] == sorted(r for r, _ in removed), (gone, removed)
        for (r, what), (_, reason) in zip(gone, sorted(removed)):
            assert reason.split()[0] in what, (r, what, reason)
        assert sorted((r, c) for r, c, _, _ in checks) == want_checks, checks
        assert any("reads two ways: 10 Mar 2026 or 3 Oct 2026" in why for *_, why in checks)
        assert len(rows) + len(gone) == len(grid) - 3  # every row under the header is kept or removed
        assert sum(1 for r, _ in log if r == truth[1]["Source row"]) == 1  # a filled, converted row logs one line
        said = dict(log)
        assert "name '  Hugo  Carter  ' -> 'Hugo Carter'" in said[truth[7]["Source row"]] and "date number" in said[truth[5]["Source row"]]
        assert all(o["Region"] for o in rows) and len(rows) == 31 and len(gone) == 7 and len(checks) == 5
        write_xlsx(rows, checks, log, out, src.name)
        wb = load_workbook(out)
        assert wb.sheetnames == ["Sales", "Monthly Summary", "Check", "Log"]
        assert [c.value for c in wb["Sales"][1]] == HEAD and wb["Sales"].max_row == 32
        assert wb["Monthly Summary"]["B5"].value.startswith('=COUNTIFS(Sales!A2:A32,">="&A5')
        assert wb["Monthly Summary"]["B7"].value == '=COUNTIFS(Sales!A2:A32,"")'
        exp = expected(rows)
        assert exp["B8"] == 31 and exp["D8"] == round(sum(o["Amount"] or 0 for o in want), 2)
    with tempfile.TemporaryDirectory() as tmp:  # typed text that looks like a formula stays text
        out = Path(tmp) / "c.xlsx"
        row = {"Date": dt.date(2026, 9, 1), "Customer": "=1+1", "Region": "", "Product": "Mug", "Qty": 1,
               "Amount": 1.0, "Source row": 4, "_check": set()}
        write_xlsx([row], [(5, "Amount", "=HYPERLINK(1)", "not an amount")], [], out, "x.xlsx")
        wb = load_workbook(out)
        assert (wb["Sales"]["B2"].value, wb["Sales"]["B2"].data_type) == ("=1+1", "s")
        assert (wb["Check"]["C2"].value, wb["Check"]["C2"].data_type) == ("=HYPERLINK(1)", "s")
        assert wb["Monthly Summary"]["B5"].data_type == "f"
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("xlsx", nargs="?", help="the messy workbook")
    ap.add_argument("-o", "--out", default="clean.xlsx")
    ap.add_argument("--sheet", help="sheet to clean (default: the first one)")
    ap.add_argument("--make-sample", metavar="XLSX", help="write the made-up messy example")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check", metavar="XLSX", help="compare the Monthly Summary with Python after Excel recalculated it")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.check:
        return check(a.check)
    if a.make_sample:
        make_sample(a.make_sample)
        return print("wrote", a.make_sample)
    if not a.xlsx:
        ap.error("give a workbook, or --selftest / --check / --make-sample")
    if Path(a.xlsx).resolve() == Path(a.out).resolve():
        sys.exit("choose another --out: the messy file is never overwritten")
    rows, checks, log = clean(*read_grid(a.xlsx, a.sheet))
    write_xlsx(rows, checks, log, a.out, Path(a.xlsx).name)
    gone = sum(1 for _, what in log if what.startswith("removed"))
    print(f"{len(rows)} rows kept, {gone} removed, {len(checks)} to check -> {a.out}")


if __name__ == "__main__":
    main()
