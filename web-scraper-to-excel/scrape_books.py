# Scrapes the public practice site books.toscrape.com into a CSV file and a formatted Excel workbook.
# The site is a sandbox made for scraping practice; its prices and ratings are made up.
# Run:
#   uv run --with requests --with beautifulsoup4 --with openpyxl python scrape_books.py -o books.xlsx --csv books.csv
#   ... --max-pages 2          quick run
#   ... --selftest             offline test of the parser and the workbook
#   ... --check books.xlsx     after Excel recalculates the file: Summary formulas vs values computed in Python
import argparse
import csv
import datetime as dt
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

START = "https://books.toscrape.com/catalogue/page-1.html"
UA = "data-automation-demos/1.0 (portfolio scraper demo)"
RATING = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
HEAD = ["Title", "Price (GBP)", "Rating", "In stock", "URL"]


def allowed(session, url):
    """True when robots.txt lets this user agent fetch url (a missing robots.txt allows everything)."""
    root = "{0.scheme}://{0.netloc}".format(urlparse(url))
    r = session.get(root + "/robots.txt", timeout=20)
    if r.status_code == 404:
        return True
    r.raise_for_status()
    rp = robotparser.RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(UA, url)


def fetch(session, url, tries=3):
    """GET with retries on network errors and 5xx; 4xx fails at once."""
    for i in range(tries):
        try:
            r = session.get(url, timeout=20)
        except (requests.ConnectionError, requests.Timeout):
            if i == tries - 1:
                raise
        else:
            if r.status_code < 500 or i == tries - 1:
                r.raise_for_status()
                r.encoding = "utf-8"  # no charset header, so requests would guess Latin-1 and turn £ into Â£
                return r.text
        time.sleep(2 ** i)


def parse(html, base):
    """Rows on one listing page, the next page URL (or None) and the total the site reports (or None)."""
    s = BeautifulSoup(html, "html.parser")
    rows = []
    for a in s.select("article.product_pod"):
        link = a.h3.a
        stars = next(c for c in a.select_one("p.star-rating")["class"] if c != "star-rating")
        rows.append({
            "title": link["title"],
            "price": float(re.search(r"\d+(?:\.\d+)?", a.select_one("p.price_color").get_text()).group()),
            "rating": RATING[stars],
            "in_stock": "In stock" in a.select_one("p.availability").get_text(),
            "url": urljoin(base, link["href"]),
        })
    nxt = s.select_one("li.next a")
    total = s.select_one("form.form-horizontal strong")
    return rows, urljoin(base, nxt["href"]) if nxt else None, int(total.get_text()) if total else None


def scrape(start, max_pages, delay):
    session = requests.Session()
    session.headers["User-Agent"] = UA
    if not allowed(session, start):
        sys.exit(f"robots.txt does not allow {start}")
    rows, seen, url, total, pages = [], set(), start, None, 0
    while url and pages < max_pages:
        page_rows, url, page_total = parse(fetch(session, url), url)
        total = total or page_total
        for r in page_rows:
            if r["url"] not in seen:
                seen.add(r["url"])
                rows.append(r)
        pages += 1
        print(f"page {pages}: {len(page_rows)} books, {len(rows)} so far")
        if url:
            time.sleep(delay)  # be polite: one request per `delay` seconds
    return rows, total, pages


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel opens the £ and accents correctly
        w = csv.writer(f)
        w.writerow(HEAD)
        w.writerows([r["title"], f"{r['price']:.2f}", r["rating"], "Yes" if r["in_stock"] else "No", r["url"]] for r in rows)


def write_xlsx(rows, path, total, source=START):
    wb = Workbook()
    ws = wb.active
    ws.title = "Books"
    ws.append(HEAD)
    for r in rows:
        ws.append([r["title"], r["price"], r["rating"], "Yes" if r["in_stock"] else "No", r["url"]])
    n = len(rows) + 1
    hfont, hfill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="2F4858")
    for c in ws[1]:
        c.font, c.fill = hfont, hfill
    for c in ws["B"][1:]:
        c.number_format = '"£"#,##0.00'
    for col in "CD":
        for c in ws[col]:
            c.alignment = Alignment(horizontal="center")
    for col, width in zip("ABCDE", (58, 12, 8, 9, 72)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:E{n}"

    sm = wb.create_sheet("Summary")
    sm["A1"] = "Books from " + urlparse(source).netloc
    sm["A1"].font = Font(bold=True, size=13)
    sm["A2"] = f"Scraped {dt.date.today().isoformat()} · practice site, made-up prices"
    b, c, d = f"Books!B2:B{n}", f"Books!C2:C{n}", f"Books!D2:D{n}"
    for i, (label, value) in enumerate([
        ("Books in this file", f"=COUNTA(Books!A2:A{n})"),
        ("Books the site reports", total),
        ("Average price", f"=AVERAGE({b})"),
        ("Cheapest", f"=MIN({b})"),
        ("Most expensive", f"=MAX({b})"),
        ("In stock", f'=COUNTIF({d},"Yes")'),
    ], start=4):
        sm[f"A{i}"], sm[f"B{i}"] = label, value
    for i in (6, 7, 8):
        sm[f"B{i}"].number_format = '"£"#,##0.00'
    sm["A11"], sm["B11"], sm["C11"] = "Rating", "Books", "Average price"
    for c_ in sm[11]:
        c_.font, c_.fill = hfont, hfill
    for k in range(1, 6):
        row = 11 + k
        sm[f"A{row}"] = f"{k} star" + ("s" if k > 1 else "")
        sm[f"B{row}"] = f"=COUNTIF({c},{k})"
        sm[f"C{row}"] = f"=IFERROR(AVERAGEIF({c},{k},{b}),\"\")"
        sm[f"C{row}"].number_format = '"£"#,##0.00'
    sm.column_dimensions["A"].width, sm.column_dimensions["B"].width, sm.column_dimensions["C"].width = 26, 12, 18
    wb.save(path)


def expected(rows):
    prices = [r["price"] for r in rows]
    by = {k: [r["price"] for r in rows if r["rating"] == k] for k in range(1, 6)}
    return {"B4": len(rows), "B6": sum(prices) / len(prices), "B7": min(prices), "B8": max(prices),
            "B9": sum(r["in_stock"] for r in rows),
            **{f"B{11 + k}": len(v) for k, v in by.items()},
            **{f"C{11 + k}": sum(v) / len(v) for k, v in by.items() if v}}


def check(path):
    """After Excel has recalculated the workbook: every Summary value must match Python's own numbers."""
    wb = load_workbook(path, data_only=True)
    rows = [{"price": r[1], "rating": r[2], "in_stock": r[3] == "Yes"}
            for r in wb["Books"].iter_rows(min_row=2, values_only=True) if r[0]]
    sm = wb["Summary"]
    for cell, want in expected(rows).items():
        got = sm[cell].value
        assert got is not None, f"{cell} has no cached value: open and save the file in Excel first"
        assert abs(float(got) - want) < 1e-9, (cell, got, want)
    reported = sm["B5"].value
    assert reported in (None, len(rows)), f"file has {len(rows)} books, the site reports {reported}"
    print(f"check ok: {len(rows)} books, Summary formulas match Python, site total {reported}")


FIXTURE = """<html><body><form class="form-horizontal"><strong>2</strong> results - showing <strong>1</strong> to <strong>2</strong>.</form>
<article class="product_pod"><h3><a href="a-light-in-the-attic_1000/index.html" title="A Light in the Attic">A Light...</a></h3>
<p class="star-rating Three"></p><div class="product_price"><p class="price_color">£51.77</p>
<p class="instock availability"><i class="icon-ok"></i> In stock</p></div></article>
<article class="product_pod"><h3><a href="tipping-the-velvet_999/index.html" title="Tipping the Velvet">Tipping...</a></h3>
<p class="star-rating One"></p><div class="product_price"><p class="price_color">Â£53.74</p>
<p class="availability">Out of stock</p></div></article>
<ul class="pager"><li class="next"><a href="page-2.html">next</a></li></ul></body></html>"""


def selftest():
    base = "https://books.toscrape.com/catalogue/page-1.html"
    rows, nxt, total = parse(FIXTURE, base)
    assert [r["title"] for r in rows] == ["A Light in the Attic", "Tipping the Velvet"], rows
    assert [r["price"] for r in rows] == [51.77, 53.74]  # also reads a price mangled by a wrong encoding guess
    assert [r["rating"] for r in rows] == [3, 1] and [r["in_stock"] for r in rows] == [True, False]
    assert rows[0]["url"] == "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    assert nxt == "https://books.toscrape.com/catalogue/page-2.html" and total == 2
    assert parse("<html></html>", base) == ([], None, None)
    exp = expected(rows)
    assert exp["B4"] == 2 and abs(exp["B6"] - 52.755) < 1e-9 and exp["B12"] == 1 and exp["B14"] == 1 and "C13" not in exp
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.xlsx"
        write_xlsx(rows, p, total)
        wb = load_workbook(p)
        assert [c.value for c in wb["Books"][1]] == HEAD and wb["Books"]["B3"].value == 53.74
        assert wb["Summary"]["B4"].value == "=COUNTA(Books!A2:A3)" and wb["Summary"]["B5"].value == 2
        write_csv(rows, Path(tmp) / "t.csv")
        lines = (Path(tmp) / "t.csv").read_text(encoding="utf-8-sig").splitlines()
        assert lines[0] == ",".join(HEAD) and lines[2].startswith("Tipping the Velvet,53.74,1,No,")
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out", default="books.xlsx")
    ap.add_argument("--csv")
    ap.add_argument("--start", default=START)
    ap.add_argument("--max-pages", type=int, default=100)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check", metavar="XLSX")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.check:
        return check(a.check)
    rows, total, pages = scrape(a.start, a.max_pages, a.delay)
    if not rows:
        sys.exit("no books found: has the page layout changed?")
    write_xlsx(rows, a.out, total, a.start)
    if a.csv:
        write_csv(rows, a.csv)
    note = f" (the site reports {total})" if total and len(rows) != total else ""
    print(f"wrote {len(rows)} books from {pages} pages to {a.out}" + (f" and {a.csv}" if a.csv else "") + note)


if __name__ == "__main__":
    main()
