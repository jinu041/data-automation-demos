# PDF / CSV tables -> one clean Excel sheet, with totals checked against the source.
# Run:       uv run --with openpyxl --with pymupdf python pdf2xlsx.py input.pdf [more.pdf table.csv ...] -o result.xlsx
# Self-test: uv run --with openpyxl --with pymupdf python pdf2xlsx.py --selftest
# - Text PDFs: table cells are located with PyMuPDF find_tables. Scans and photos are first typed into a UTF-8 CSV.
# - Unreadable cells are written as [?] in the CSV. In Excel they become blank yellow cells and are listed on a
#   Notes sheet (never guessed).
# - Rows starting with "Total" (or Korean 합계) leave the data and go to a Check sheet: SUM formulas vs source totals.
# - The first row of the first table is the header. Header rows repeated on later pages are dropped.
import argparse
import csv
import re
import sys
from pathlib import Path

UNREAD = "[?]"
TOTAL = ("total", "grand total", "sum", "합계", "총계", "총합")


def norm(row):
    return [re.sub(r"\s+", " ", str(c or "")).strip() for c in row]


def parse(s):
    """'1,234.50' '$12' '(3.00)' '12%' -> numbers. Dates, codes with leading zeros and text stay as they are."""
    t = s.replace(" ", "")
    neg = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("()-").lstrip("$€£₩")
    pct = t.endswith("%")
    t = t.rstrip("%")
    if not re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?|\d+(\.\d+)?", t) or (len(t) > 1 and t[0] == "0" and t[1].isdigit()):
        return s, False
    x = float(t.replace(",", ""))
    x = -x if neg else x
    return (x / 100 if pct else x), pct


def read_rows(path):
    if path.suffix.lower() == ".csv":
        with open(path, encoding="utf-8-sig", newline="") as f:
            return [(f"{path.name}", norm(r)) for r in csv.reader(f)]
    import pymupdf
    out = []
    with pymupdf.open(path) as doc:
        for pno, page in enumerate(doc, 1):
            for t in page.find_tables().tables:
                # Take only the cell boxes from find_tables and read each cell's text with MuPDF's own extraction:
                # t.extract() read '1.50' as '150 .' and 'Item 1' as 'Item1' in testing.
                for row in t.rows:
                    cells = (page.get_text("text", clip=pymupdf.Rect(b)) if b else "" for b in row.cells)
                    out.append((f"{path.name} p{pno}", norm(cells)))
    return out


def build(inputs):
    raw = [r for p in inputs for r in read_rows(p)]
    if not raw:
        sys.exit("No table found. For a scanned PDF, type the table into a CSV first.")
    header = raw[0][1]
    data, totals = [], []
    for src, r in raw[1:]:
        if r == header or not any(r):
            continue
        first = next(c for c in r if c).lower()
        (totals if first.startswith(TOTAL) else data).append((src, r))
    return header, data, totals


def write(header, data, totals, out):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter as L

    yellow = PatternFill("solid", start_color="FFF2CC", end_color="FFF2CC")
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", start_color="E7E6E6", end_color="E7E6E6")
    n = len(header)
    notes, cols = [], [[] for _ in range(n)]  # cols: parsed values per column (for the total check)
    for i, (src, r) in enumerate(data, 2):
        if len(r) != n:
            notes.append(f"Row {i} ({src}): {len(r)} cells, header has {n}. Please check this row.")
        for j, s in enumerate((r + [""] * n)[:n], 1):
            v, pct = parse(s)
            c = ws.cell(i, j, None if v in ("", UNREAD) else v)
            if v == UNREAD:
                c.fill = yellow
                notes.append(f"{L(j)}{i} ({src}): unreadable in the source, left blank.")
            elif pct:
                c.number_format = "0.0%"
            cols[j - 1].append(v)
    last = len(data) + 1
    # Number format per column: if any value has decimals, the whole column gets 0.00 (no '42' next to '38.40')
    for j, vals in enumerate(cols, 1):
        nums = [v for v in vals if isinstance(v, float)]
        fmt = "#,##0.00" if any(not v.is_integer() for v in nums) else "#,##0"
        for i in range(2, last + 1):
            c = ws.cell(i, j)
            if isinstance(c.value, float) and c.number_format != "0.0%":
                c.number_format = fmt
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{L(n)}{last}"
    for j in range(1, n + 1):
        width = max(len(str(ws.cell(i, j).value or "")) for i in range(1, last + 1))
        ws.column_dimensions[L(j)].width = min(50, width + 3)

    # Check numeric columns only: SUM of the rows (formula) vs the source Total row
    src_total = dict(enumerate(norm(totals[-1][1]))) if totals else {}
    ck = wb.create_sheet("Check")
    ck.append(["Column", "Sum of rows", "Source total", "Difference", "Result"])
    for c in ck[1]:
        c.font = Font(bold=True)
    results = []
    for j, vals in enumerate(cols):
        nums = [v for v in vals if v not in ("", UNREAD)]
        if not nums or not all(isinstance(v, float) for v in nums):
            continue
        k = ck.max_row + 1
        st, _ = parse(src_total.get(j, ""))
        st = st if isinstance(st, float) else None
        ck.append([header[j], f"=SUM(Data!{L(j + 1)}2:{L(j + 1)}{last})", st,
                   f'=IF(C{k}="","",B{k}-C{k})', f'=IF(C{k}="","no source total",IF(ABS(D{k})<0.005,"OK","CHECK"))'])
        results.append((header[j], round(sum(nums), 2), st))
    ck.append([])
    ck.append(["Rows", len(data)])
    ck.column_dimensions["A"].width = 24
    ck.column_dimensions["E"].width = 18
    if notes:
        ns = wb.create_sheet("Notes")
        ns.append(["Notes"])
        for t in notes:
            ns.append([t])
        ns.column_dimensions["A"].width = 90
    wb.properties.creator = ""
    wb.properties.lastModifiedBy = ""
    wb.save(out)
    return results, notes


def selftest():
    import tempfile
    import pymupdf as fitz

    tmp = Path(tempfile.mkdtemp())
    head = ["Item", "Qty", "Price", "Total"]
    rows = [[f"Item {k}", str(k), f"{k * 1.5:,.2f}", f"{k * k * 1.5:,.2f}"] for k in range(1, 41)]
    grand = f"{sum(k * k * 1.5 for k in range(1, 41)):,.2f}"  # 33,210.00
    doc = fitz.open()
    for chunk in (rows[:20], rows[20:] + [["Total", "", "", grand]]):  # two pages, header repeated
        page = doc.new_page()
        tbl, x0, y0, w, h = [head] + chunk, 50, 50, 120, 18
        for i, r in enumerate(tbl):
            for j, s in enumerate(r):
                page.insert_text((x0 + j * w + 4, y0 + i * h + 13), s, fontsize=10)
        for i in range(len(tbl) + 1):
            page.draw_line((x0, y0 + i * h), (x0 + 4 * w, y0 + i * h))
        for j in range(5):
            page.draw_line((x0 + j * w, y0), (x0 + j * w, y0 + len(tbl) * h))
    doc.save(tmp / "sample.pdf")
    header, data, totals = build([tmp / "sample.pdf"])
    assert header == head, header
    assert len(data) == 40 and len(totals) == 1, (len(data), len(totals))
    results, notes = write(header, data, totals, tmp / "out.xlsx")
    assert ("Total", 33210.0, 33210.0) in results, results
    assert not notes, notes

    (tmp / "scan.csv").write_text("Name,Amount\nA,\"1,000\"\nB,[?]\nC,(250.50)\n합계,749.50\n", encoding="utf-8")
    header, data, totals = build([tmp / "scan.csv"])
    results, notes = write(header, data, totals, tmp / "scan.xlsx")
    assert results == [("Amount", 749.5, 749.5)], results
    assert len(notes) == 1 and notes[0].startswith("B3"), notes
    assert parse("007") == ("007", False) and parse("2026-11-09") == ("2026-11-09", False)
    assert parse("12%") == (0.12, True) and parse("$1,234.5") == (1234.5, False)

    from openpyxl import load_workbook
    wb = load_workbook(tmp / "out.xlsx")
    assert wb.properties.creator in ("", None) and wb["Data"]["D41"].value == 2400.0
    assert wb["Data"]["D2"].number_format == "#,##0.00" and wb["Data"]["B2"].number_format == "#,##0"  # per-column format
    print("selftest ok:", tmp)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="*", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        sys.exit()
    if not a.inputs or not a.out:
        ap.error("give input files and -o result.xlsx")
    header, data, totals = build(a.inputs)
    results, notes = write(header, data, totals, a.out)
    print(f"{len(data)} rows → {a.out}")
    for name, s, st in results:
        print(f"  {name}: sum {s:,.2f}" + ("" if st is None else f" / source {st:,.2f} {'OK' if abs(s - st) < 0.005 else 'CHECK'}"))
    for t in notes:
        print("  NOTE", t)
