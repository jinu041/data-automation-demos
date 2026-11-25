# Pull invoice data out of PDFs with Claude (Python)

`extract.py` reads quote and invoice PDFs and builds an Excel workbook with one row per document (vendor, document number, date, currency, subtotal, tax, total) and one row per line item. Then it checks the math on every document: quantity × unit price for each line, the lines against the subtotal, and subtotal + tax against the total.

It runs two ways:

- **Live mode** (`--live`) sends the text of each PDF to Claude in batches of 3 and asks for JSON that must match a fixed schema (structured outputs), so every document comes back with the same fields. Only the text is sent, not images. If a batch gets cut off, it is split in half and retried. If Claude declines a batch, those documents are read by the rules instead and say "Rules (fallback)" in the Method column.
- **Mock mode** (the default) reads the documents with label rules, so you can try the whole flow without an API key. The rules only know the three sample layouts. Live mode is what handles other layouts.

Either way, the numbers are checked in Python with exact decimal math (cents, rounded half up), never by the model.

## What the workbook contains

- **Documents**: file, type, vendor, document number, date (a real Excel date), currency, number of lines, subtotal, tax, total, sum of the lines, the Python check, an Excel check formula and the method. A failed Python check is shaded red.
- **Line items**: file, vendor, description, details, quantity, unit price, amount and a line check formula.

The Excel checks are formulas, so they update when someone corrects a value by hand.

## Run it

```
uv run --with pymupdf --with openpyxl python extract.py --make-input
uv run --with pymupdf --with openpyxl python extract.py
uv run --with pymupdf --with openpyxl python extract.py --selftest
uv run --with pymupdf --with openpyxl --with anthropic python extract.py --live
```

`-i` chooses another folder of PDFs and `-o` another output file. Live mode needs Python 3.10+ and your own API key in the `ANTHROPIC_API_KEY` environment variable. The official `anthropic` SDK reads the key from there, and the script never prints it or writes it to a file. Live results are saved as JSON next to the workbook before the workbook is built. The live run uses `claude-opus-5-5` at low effort and turns on the API's server-side fallback, which retries on another model if the first one declines a request.

Scanned PDFs and photos have no text layer, so they need OCR first. This demo doesn't do OCR.

## The example

`sample/` holds 6 made-up PDFs in three layouts:

- two US quotes, with a dollar sign in every cell and dates like "November 3, 2026"
- two UK VAT invoices in pounds, with a VAT column on every line and dates like "5 Nov 2026"
- two US invoices with a "Rate" column and dates like "11/10/2026"

`05_vat_invoice_copperleaf.pdf` contains a made-up seller's mistake: 3 × £6.45 is printed as £19.53 instead of £19.35, and the totals were added up from that wrong line. The totals agree with each other, so only the line check catches it. `sample/extract_mock.xlsx` is the mock-mode result: 5 documents OK, and 05 flagged as `MISMATCH: Instant coffee: qty x price`.

## How it was checked

- `--selftest` builds the 6 PDFs in a temporary folder and checks that the rules read every field of all 6 exactly, that the check flags the typo in 05 and two values changed on purpose, and that the PDFs carry no author or producer details. It runs the live-mode code against a stand-in client (no key, no network) to check that a cut-off batch is split and retried and that a declined batch falls back to the rules. It also opens the written workbook and checks the sheets, the formulas and that no author name is stored.
- `sample/extract_mock.xlsx` was recalculated in Excel. The Excel check matched the Python check on all 6 documents, and the coffee line in 05 was the only line marked CHECK.
- The files in `sample/` come from mock mode. Live results depend on the model. The math check catches wrong numbers, but not a wrong vendor name or date, so a person should look over the sheet before using it.

## How this was made

Built and tested with Claude, an AI agent. All companies, documents and amounts are made up. This demo is not affiliated with Anthropic.
