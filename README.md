# Data and automation demos

Small, tested demos: spreadsheets that do the math, plus Python, C++ and Java tools that clean, convert and serve data. Sample data is made up, except the public ECB exchange rates.

| Demo | What it shows |
|---|---|
| [lead-tracker](lead-tracker) | Lead tracker for a small service business: follow-up flags, Google Calendar reminder links and a dashboard (Excel + Google Sheets, formulas only) |
| [pdf-tables-to-excel](pdf-tables-to-excel) | Python: PDF tables to one clean Excel sheet, with the totals checked against the source |
| [fx-daily-report](fx-daily-report) | Python: daily report from a public API (ECB exchange rates) straight to a formatted Excel workbook with a chart |
| [cpp-csv-summary](cpp-csv-summary) | C++17: command-line tool that groups and totals CSV data, handles quoted fields and reports bad rows by line number |
| [java-inventory-api](java-inventory-api) | Java: small inventory REST API with the JDK only, input validation, exact money math and HTTP tests |

More demos (spreadsheets and Python) are in [portfolio-demos](https://github.com/jinu041/portfolio-demos).

## How these are made

- Built and tested with Claude, an AI agent on my PC. I review the results and handle all messages.
- Every demo has a check: spreadsheet numbers are recalculated in Excel and compared with values computed separately, and scripts have self-tests.
- Names, emails and numbers in the samples are made up (the exchange-rate demo uses public ECB data). Files are cleaned of author names, file paths and printer settings before publishing.
