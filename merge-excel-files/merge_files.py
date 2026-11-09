"""Merge a folder of messy Excel and CSV exports into one clean workbook: an Orders sheet, a Summary with
live formulas and a Log of every row that was left out and why."""
import argparse
import csv
import datetime as dt
import random
import re
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

HEAD = ["Order ID", "Date", "Customer", "Product", "Qty", "Amount", "Source file"]
ALIASES = {  # header text in the exports (lower case, "_" as a space) -> our column
    "order id": "Order ID", "order no": "Order ID", "order #": "Order ID", "order number": "Order ID",
    "date": "Date", "order date": "Date",
    "customer": "Customer", "client": "Customer", "customer name": "Customer",
    "product": "Product", "item": "Product",
    "qty": "Qty", "quantity": "Qty", "units": "Qty",
    "amount": "Amount", "total": "Amount", "total ($)": "Amount", "amount ($)": "Amount", "amount usd": "Amount",
}
NEEDED = ("Order ID", "Date", "Amount")
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def norm_header(v):
    return re.sub(r"\s+", " ", str(v).replace("_", " ")).strip().lower() if v is not None else ""


def parse_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = str(v or "").strip()
    if m := re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", s):
        y, mo, d = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s):  # US exports: month/day/year
        mo, d, y = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{1,2}) ([A-Za-z]{3})[a-z]* (\d{4})", s):
        d, mo, y = int(m[1]), MONTHS.get(m[2].lower()), int(m[3])
    else:
        return None
    try:
        return dt.date(y, mo, d)
    except (TypeError, ValueError):
        return None


def parse_amount(v):
    """Numbers, '$1,250.00', 'USD 30', '(12.50)' or '-12.50' for refunds; anything else is None, never a guess."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = str(v or "").strip()
    neg = (s.startswith("(") and s.endswith(")")) or s.startswith("-")
    core = re.sub(r"(?i)usd|[$,\s()]|^-", "", s)
    return round(-float(core) if neg else float(core), 2) if re.fullmatch(r"\d+(\.\d+)?", core) else None


def parse_qty(v):
    try:
        q = float(str(v).replace(",", ""))
    except ValueError:
        return None
    return int(q) if q.is_integer() and q > 0 else None


def norm_id(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)  # Excel stores 1003 as 1003.0
    return str(v).strip() if v is not None else ""


def read_table(path):
    """Every row of a CSV file or of the first sheet of a workbook, as lists of cell values."""
    if path.suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.reader(f))
    ws = load_workbook(path, data_only=True).worksheets[0]
    return [list(r) for r in ws.iter_rows(min_row=1, values_only=True)]


def find_header(rows):
    """Index and column map of the first row (within the first 10) that names at least 3 known columns."""
    for i, row in enumerate(rows[:10]):
        cols = {}
        for j, v in enumerate(row):
            name = ALIASES.get(norm_header(v))
            if name and name not in cols:
                cols[name] = j
        if len(cols) >= 3:
            return i, cols
    return None, {}


def merge(paths):
    """Returns (orders, log): orders are dicts keyed by HEAD, log lines are (file, row, reason, values)."""
    orders, log, seen = [], [], {}
    for path in paths:
        rows = read_table(path)
        h, cols = find_header(rows)
        missing = [c for c in NEEDED if c not in cols]
        if h is None or missing:
            log.append((path.name, "", "no header row with " + ", ".join(missing or NEEDED), ""))
            continue
        for r, row in enumerate(rows[h + 1:], start=h + 2):
            cells = [v for v in row if v not in (None, "")]
            if not cells:
                continue  # blank row
            get = lambda c: row[cols[c]] if c in cols and cols[c] < len(row) else None  # noqa: E731
            values = " | ".join(str(v.date() if isinstance(v, dt.datetime) else v) for v in cells)
            oid = norm_id(get("Order ID"))
            if not oid:
                total = any(str(v).strip().lower().startswith("total") for v in cells)
                log.append((path.name, r, "totals row" if total else "no order ID", values))
                continue
            date, amount = parse_date(get("Date")), parse_amount(get("Amount"))
            qty = parse_qty(get("Qty")) if "Qty" in cols else None
            problems = [p for p, bad in (("bad date", date is None), ("bad amount", amount is None),
                                         ("bad quantity", "Qty" in cols and qty is None)) if bad]
            if problems:
                log.append((path.name, r, ", ".join(problems), values))
            elif oid in seen:
                log.append((path.name, r, f"duplicate order ID, kept {seen[oid]}", values))
            else:
                seen[oid] = f"{path.name} row {r}"
                orders.append({"Order ID": oid, "Date": date, "Customer": str(get("Customer") or "").strip(),
                               "Product": str(get("Product") or "").strip(), "Qty": qty, "Amount": amount,
                               "Source file": path.name})
    orders.sort(key=lambda o: (o["Date"], o["Order ID"]))
    return orders, log


def input_files(folder):
    return sorted(p for p in Path(folder).iterdir()
                  if p.suffix.lower() in (".xlsx", ".csv") and not p.name.startswith("~$"))


def layout(orders):
    """Months and source files in the order the Summary lists them, and the row where the file table starts."""
    months = sorted({o["Date"].replace(day=1) for o in orders})
    return months, sorted({o["Source file"] for o in orders}), 10 + len(months) + 1


def write_xlsx(orders, log, path, n_files):
    wb = Workbook()
    hfont, hfill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E78")
    ws = wb.active
    ws.title = "Orders"
    ws.append(HEAD)
    for o in orders:
        ws.append([o[h] for h in HEAD])
    n = max(len(orders) + 1, 2)
    for c in ws[1]:
        c.font, c.fill = hfont, hfill
    for r in range(2, n + 1):
        ws[f"B{r}"].number_format = "yyyy-mm-dd"
        ws[f"F{r}"].number_format = "#,##0.00"
    for col, width in zip("ABCDEFG", (10, 12, 18, 21, 6, 11, 17)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:G{n}"

    sm = wb.create_sheet("Summary")
    sm["A1"] = "Merged orders"
    sm["A1"].font = Font(bold=True, size=13)
    sm["A2"] = f"{n_files} files merged {dt.date.today().isoformat()}"
    d, e, f, g = (f"Orders!{c}2:{c}{n}" for c in "BEFG")
    for i, (label, value) in enumerate([("Orders", f"=COUNTA(Orders!A2:A{n})"), ("Units", f"=SUM({e})"),
                                        ("Total amount", f"=SUM({f})"), ("Rows left out (Log)", len(log))], start=4):
        sm[f"A{i}"], sm[f"B{i}"] = label, value
    sm["B6"].number_format = "#,##0.00"
    months, sources, top = layout(orders)
    for k, m in enumerate(months, start=10):
        sm[f"A{k}"], sm[f"A{k}"].number_format = m, "mmm yyyy"
        sm[f"B{k}"] = f'=COUNTIFS({d},">="&A{k},{d},"<"&EDATE(A{k},1))'
        sm[f"C{k}"] = f'=SUMIFS({f},{d},">="&A{k},{d},"<"&EDATE(A{k},1))'
    for k, s in enumerate(sources, start=top + 1):
        sm[f"A{k}"], sm[f"B{k}"], sm[f"C{k}"] = s, f"=COUNTIF({g},A{k})", f"=SUMIF({g},A{k},{f})"
    for head_row, first in ((9, "Month"), (top, "Source file")):
        for col, text in zip("ABC", (first, "Orders", "Amount")):
            sm[f"{col}{head_row}"] = text
            sm[f"{col}{head_row}"].font, sm[f"{col}{head_row}"].fill = hfont, hfill
    for k in range(10, top + len(sources) + 1):
        sm[f"C{k}"].number_format = "#,##0.00"
    for col, width in zip("ABC", (22, 9, 12)):
        sm.column_dimensions[col].width = width

    lg = wb.create_sheet("Log")
    lg.append(["File", "Row", "Reason", "Values in the row"])
    for line in log:
        lg.append(list(line))
    for c in lg[1]:
        c.font, c.fill = hfont, hfill
    for col, width in zip("ABCD", (16, 6, 40, 70)):
        lg.column_dimensions[col].width = width
    wb.save(path)


def expected(orders, n_log):
    months, sources, top = layout(orders)
    amount = lambda rows: round(sum(o["Amount"] for o in rows), 2)  # noqa: E731
    exp = {"B4": len(orders), "B5": sum(o["Qty"] or 0 for o in orders), "B6": amount(orders), "B7": n_log}
    for k, m in enumerate(months, start=10):
        rows = [o for o in orders if o["Date"].replace(day=1) == m]
        exp[f"B{k}"], exp[f"C{k}"] = len(rows), amount(rows)
    for k, s in enumerate(sources, start=top + 1):
        rows = [o for o in orders if o["Source file"] == s]
        exp[f"B{k}"], exp[f"C{k}"] = len(rows), amount(rows)
    return exp


def check(path):
    """After Excel has recalculated the workbook: every Summary value must match Python's own numbers."""
    wb = load_workbook(path, data_only=True)
    orders = [dict(zip(HEAD, (r[0], r[1].date() if isinstance(r[1], dt.datetime) else r[1], *r[2:7])))
              for r in wb["Orders"].iter_rows(min_row=2, values_only=True) if r[0] is not None]
    n_log = wb["Log"].max_row - 1
    sm = wb["Summary"]
    for cell, want in expected(orders, n_log).items():
        got = sm[cell].value
        assert got is not None, f"{cell} has no cached value: open and save the file in Excel first"
        assert abs(float(got) - want) < 1e-6, (cell, got, want)
    print(f"check ok: {len(orders)} orders, {n_log} rows in the Log, every Summary value matches Python")


def make_samples(folder):
    """Three made-up exports with the usual problems: other header names and order, a title row, a totals row,
    text amounts, a blank row, a day-first date in a US file, 'n/a' and the same orders exported twice."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(7)
    customers = ["Maple Cafe", "Harbor Bakery", "Pine Street Deli", "Blue Door Bistro", "Corner Books", "Sunny Juice Bar"]
    prices = {"Espresso beans 1kg": 24.5, "Paper cups (1000)": 39.0, "Oat milk case": 18.75, "Grinder cleaning kit": 12.0}

    def order(oid, day):
        p, q = rnd.choice(list(prices)), rnd.randint(1, 6)
        return [oid, dt.date(2026, 9, 1) + dt.timedelta(days=day), rnd.choice(customers), p, q, round(prices[p] * q, 2)]

    east = [order(1000 + k, k * 4) for k in range(12)]
    west = [order(1020 + k, k * 5 + 2) for k in range(10)]
    online = [order(1040 + k, k * 5 + 1) for k in range(10)]

    wb = Workbook()
    ws = wb.active
    ws.append(["East branch orders, September to October 2026"])
    ws.append([])
    ws.append(["Order ID", "Order date", "Client", "Item", "Quantity", "Total ($)"])
    for r in east:
        ws.append(r)
    ws.append([None, None, None, None, "Total", round(sum(r[5] for r in east), 2)])
    for col, width in zip("ABCDEF", (10, 12, 18, 21, 9, 10)):
        ws.column_dimensions[col].width = width
    wb.save(folder / "east_branch.xlsx")

    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "Order #", "Product", "Units", "Amount", "Customer"])
    for k, (oid, day, cust, prod, qty, amt) in enumerate(west):
        date = "31/10/2026" if k == 7 else f"{day.month:02d}/{day.day:02d}/{day.year}"  # k 7: a day-first date
        ws.append([date, oid, prod, qty, f"${amt:,.2f}" if k % 2 else amt, cust])
        if k == 4:
            ws.append([])
    for col, width in zip("ABCDEF", (12, 9, 21, 7, 10, 18)):
        ws.column_dimensions[col].width = width
    wb.save(folder / "west_branch.xlsx")

    with open(folder / "online_shop.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["order_id", "date", "customer_name", "item", "qty", "amount_usd"])
        for k, (oid, day, cust, prod, qty, amt) in enumerate(online):
            w.writerow([oid, day.isoformat(), cust, prod, qty, "n/a" if k == 3 else f"{amt:.2f}"])
        for oid, day, cust, prod, qty, amt in (east[3], east[7]):  # the same orders exported twice
            w.writerow([oid, day.isoformat(), cust, prod, qty, f"{amt:.2f}"])
    return east, west, online


def selftest():
    assert parse_date("10/03/2026") == dt.date(2026, 10, 3) and parse_date("2026.11.05") == dt.date(2026, 11, 5)
    assert parse_date("5 Mar 2026") == dt.date(2026, 3, 5) and parse_date("31/10/2026") is None
    assert parse_date(dt.datetime(2026, 9, 2, 0, 0)) == dt.date(2026, 9, 2) and parse_date("soon") is None
    assert parse_amount("$1,250.00") == 1250.0 and parse_amount("USD 30") == 30.0 and parse_amount("(12.50)") == -12.5
    assert parse_amount("-7") == -7.0 and parse_amount("n/a") is None and parse_amount("12k") is None
    assert parse_amount("") is None and parse_amount(True) is None and parse_amount(3) == 3.0
    assert parse_qty("2") == 2 and parse_qty(3.0) == 3 and parse_qty("1.5") is None and parse_qty("0") is None
    assert norm_id(1003.0) == "1003" and norm_header(" Amount_USD ") == "amount usd"
    with tempfile.TemporaryDirectory() as tmp:
        east, west, online = make_samples(tmp)
        files = input_files(tmp)
        assert [p.name for p in files] == ["east_branch.xlsx", "online_shop.csv", "west_branch.xlsx"]
        orders, log = merge(files)
        assert len(orders) == 12 + 9 + 9, len(orders)
        reasons = [(f, reason.split(",")[0]) for f, _, reason, _ in log]
        assert reasons == [("east_branch.xlsx", "totals row"), ("online_shop.csv", "bad amount"),
                           ("online_shop.csv", "duplicate order ID"), ("online_shop.csv", "duplicate order ID"),
                           ("west_branch.xlsx", "bad date")], reasons
        assert log[0][1] == 16 and log[4][1] == 10  # row numbers as Excel shows them (title, blank row counted)
        assert len({o["Order ID"] for o in orders}) == len(orders)
        assert [o["Date"] for o in orders] == sorted(o["Date"] for o in orders)
        want_total = round(sum(r[5] for r in east) + sum(r[5] for k, r in enumerate(west) if k != 7)
                           + sum(r[5] for k, r in enumerate(online) if k != 3), 2)
        assert expected(orders, len(log))["B6"] == want_total
        out = Path(tmp) / "merged.xlsx"
        write_xlsx(orders, log, out, len(files))
        wb = load_workbook(out)
        assert [c.value for c in wb["Orders"][1]] == HEAD and wb["Summary"]["B4"].value == "=COUNTA(Orders!A2:A31)"
        assert wb["Summary"]["B10"].value.startswith("=COUNTIFS(Orders!B2:B31") and wb["Log"].max_row == 6
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", nargs="?", help="folder with .xlsx and .csv exports")
    ap.add_argument("-o", "--out", default="merged.xlsx")
    ap.add_argument("--make-samples", metavar="DIR", help="write the made-up example exports")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check", metavar="XLSX")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.check:
        return check(a.check)
    if a.make_samples:
        make_samples(a.make_samples)
        return print("wrote", ", ".join(p.name for p in input_files(a.make_samples)))
    if not a.folder:
        ap.error("give a folder, or --selftest / --check / --make-samples")
    files = input_files(a.folder)
    if not files:
        sys.exit("no .xlsx or .csv files in " + a.folder)
    orders, log = merge(files)
    write_xlsx(orders, log, a.out, len(files))
    print(f"merged {len(orders)} orders from {len(files)} files into {a.out}")
    for f, r, reason, _ in log:
        print(f"  left out: {f} row {r}: {reason}")


if __name__ == "__main__":
    main()
