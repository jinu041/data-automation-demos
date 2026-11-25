# Sort customer messages with Claude (Python)

`triage.py` reads customer messages from a CSV file and builds an Excel review queue. Each message gets a category, an urgency level, a sentiment, a one-line summary and a reply draft. Replies stay as drafts marked "Pending review", and the script never sends anything.

It runs two ways:

- **Live mode** (`--live`) sends the messages to Claude in batches of 20 and asks for JSON that must match a fixed schema (structured outputs), so every answer comes back with a valid category, urgency and sentiment. If a batch gets cut off, it is split in half and retried. If Claude declines a batch, those messages fall back to the rules and say "Rules (fallback)" in the Method column, so nothing goes missing.
- **Mock mode** (the default) uses simple keyword rules instead, so you can try the whole flow without an API key.

## What the workbook contains

- **Inquiries**: ID, received date, channel, customer, message, category, urgency, sentiment, summary, reply status and method, with filters on and High urgency highlighted
- **Summary**: counts by category, urgency and sentiment as `COUNTIFS` formulas, plus a check cell that compares the number of messages with the sum of the categories
- **Reply drafts**: the draft for each message, a Status drop-down (Pending review, Approved, Needs edit, On hold), and Reviewer and Notes columns

## Run it

```
uv run --with openpyxl python triage.py --make-input
uv run --with openpyxl python triage.py
uv run --with openpyxl python triage.py --selftest
uv run --with openpyxl --with anthropic python triage.py --live
```

`-i` and `-o` choose other input and output files. Live mode needs Python 3.10+ and your own API key in the `ANTHROPIC_API_KEY` environment variable. The official `anthropic` SDK reads the key from there, and the script never prints it or writes it to a file. The live run uses `claude-opus-5-5` at low effort and turns on the API's server-side fallback, which retries on another model if the first one declines a request.

## The example

`sample/inquiries.csv` holds 60 made-up messages to a fictional store, Acme Home Goods: late deliveries, returns, double charges, product questions, damaged items, praise and a few general questions. `sample/triage_mock.xlsx` is the mock-mode result. It sorts the 60 messages into 12 High, 32 Normal and 16 Low, with 18 negative messages, and the check cell shows OK.

## How it was checked

- `--selftest` builds the 60 messages from a fixed seed and checks that the rules put every one of them in its intended category and that damaged items are always High. It runs the live-mode code against a stand-in client (no key, no network) to check that a cut-off batch is split and retried and that a declined batch falls back to the rules. It also opens the written workbook and checks the sheets, a formula, the drop-down and that no author name is stored.
- `sample/triage_mock.xlsx` was recalculated in Excel, and every Summary value was compared with counts made separately in Python from the Inquiries sheet. All matched.
- The files in `sample/` come from mock mode. Live-mode results depend on the model and can be wrong, so a person should read every draft before it goes out.

## How this was made

Built and tested with Claude, an AI agent. All messages, names and order numbers are made up. This demo is not affiliated with Anthropic.
