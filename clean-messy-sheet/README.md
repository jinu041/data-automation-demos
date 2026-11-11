# Clean a messy sales sheet (Python)

`clean_sheet.py` turns a hand-typed sales log into one flat table you can sort, filter and pivot. Merged cells are filled in, every date becomes a real date, names typed in two columns are joined, and the rows that break a pivot table (subtotals, repeated headers, blank rows, rows pasted twice) are removed. Anything it can't decide for sure goes on a **Check** sheet instead of being guessed, and every change is listed on a **Log** sheet. The messy file is never overwritten.

## What it does

- Finds the header row under a title line and matches different names for the same column (`Order date`, `Client`, `Surname`, `Units`, `Area` ...). The names live in one dictionary at the top of the script.
- Fills merged cells, such as a Region typed once and merged down a block of rows
- Reads dates as real dates: Excel dates and date numbers, `2026-09-03`, `09/17/2026`, `Sep 3, 2026`, `3 Sep 2026`, `03-Sep-2026`. For `a/b/yyyy` dates where both readings are possible, it uses the order that the column's unambiguous dates agree on. A date that still reads two ways (`03.10.2026`: 3 Oct or 10 Mar?) or can't exist (`09/31/2026`) goes to **Check**.
- Joins first and last names and fixes stray caps and spaces (`  anna `, `SMITH` → `Anna Smith`), but leaves names typed in mixed case (`McDonald`) as they are
- Reads amounts typed as text (`$1,250.00`, `USD 30`) and refunds in brackets (`(24.50)` → -24.50). `n/a`, `12k` or a quantity like `2 boxes` goes to **Check**.
- Removes subtotal and total rows, repeated header rows, blank rows and exact duplicates, each with a line on the **Log** sheet. When two rows have the same customer, date and product but a different quantity or amount (a corrected entry typed under the original), both are kept and the second one goes to **Check** with "keep both?".
- Writes four sheets:
  - **Sales**: one row per sale, sorted by date, with the source row number, a frozen header and filters. Cells listed on Check are highlighted.
  - **Monthly Summary**: orders, units and amount by month, a line for rows with no date yet and a total, all as `COUNTIFS` / `SUMIFS` / `SUM` formulas that keep working when you edit the Sales sheet
  - **Check**: every cell it would not guess, with the reason
  - **Log**: every change and every removed row

## Run it

```
uv run --with openpyxl python clean_sheet.py sample/messy_sales.xlsx -o clean.xlsx
uv run --with openpyxl python clean_sheet.py --make-sample my_messy.xlsx
uv run --with openpyxl python clean_sheet.py --selftest
uv run --with openpyxl python clean_sheet.py --check clean_recalculated.xlsx
```

## The example

`sample/messy_sales.xlsx` is a made-up sales log for September and October 2026 with 30 sales and the problems hand-kept sheets have: a merged title, Region merged down two blocks, dates typed six ways (plus one that reads two ways and one that can't exist), names in two columns with stray caps and spaces, amounts as text, a refund in brackets, `n/a`, `2 boxes`, two subtotal rows and a grand total, a repeated header, a blank row, two rows pasted a second time and a corrected entry typed under the original.

The result, `sample/clean_sales.xlsx`, keeps 31 rows (the 30 sales plus the corrected entry), removes 7 and lists 5 cells to check.

## How it was checked

- `--selftest` builds the example in a temporary folder from known values, cleans it and compares every kept row with those values. It also checks every removed row number and reason, the five Check cells (including the two-way date), the sheet names and formulas in the written workbook, that text typed like a formula (`=1+1`) stays text, and the date, amount, quantity and name readers on edge cases.
- `sample/clean_sales.xlsx` was recalculated in Excel, and `--check` compared every Monthly Summary value with numbers computed separately in Python from the Sales sheet. All matched.

## How this was made

Built and tested with Claude, an AI agent. The data is made up.
