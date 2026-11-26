"""Write the three made-up invoice PDFs (samples/) and workflow.json, which carries them for the demo run.

Invoice PC-3315 has a wrong subtotal on purpose, so the check has something to catch.
"""
import base64, json, pathlib
import fitz  # PyMuPDF

HERE = pathlib.Path(__file__).resolve().parent
INVOICES = [  # vendor, sender, number, date, tax rate, lines (description, qty, unit price), printed subtotal if wrong
    ("Northwind Office Supply", "billing@northwind.example", "INV-1041", "2026-11-03", 10,
     [("A4 copy paper, box of 5 reams", 4, 28.50), ("Black toner cartridge", 2, 64.00), ("Desk organiser", 3, 12.90)], None),
    ("Harbor Print Co.", "accounts@harborprint.example", "HP-2207", "2026-11-10", 8,
     [("Business cards, 500 pcs", 2, 45.00), ("A5 flyers, 1,000 pcs", 1, 120.00)], None),
    ("Peak Cloud Hosting", "invoices@peakcloud.example", "PC-3315", "2026-11-15", 0,
     [("Hosting plan, November", 1, 49.00), ("Extra storage 50 GB", 2, 7.50), ("Domain renewal", 1, 18.00)], 92.00),
]
EMAILS = [  # the demo's two mails: the first carries two PDFs
    {"from": "billing@northwind.example", "subject": "Invoices for November", "files": ["INV-1041.pdf", "HP-2207.pdf"]},
    {"from": "invoices@peakcloud.example", "subject": "Your Peak Cloud invoice PC-3315", "files": ["PC-3315.pdf"]},
]


def write_pdf(vendor, sender, number, date, rate, lines, printed_subtotal):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    t = lambda x, y, s, size=10, font="helv": page.insert_text((x, y), s, fontsize=size, fontname=font)
    money = lambda v: f"{v:,.2f}"
    t(50, 70, vendor, 18, "hebo"); t(50, 90, sender)
    t(400, 70, "INVOICE", 18, "hebo"); t(400, 92, f"Invoice no: {number}"); t(400, 106, f"Date: {date}")
    t(50, 140, "Bill to: Brightwave Studio, 12 Example Street")
    y = 180
    for x, head in ((50, "Description"), (330, "Qty"), (390, "Unit price"), (480, "Amount")):
        t(x, y, head, 10, "hebo")
    page.draw_line((50, y + 6), (545, y + 6))
    subtotal = 0
    for desc, qty, unit in lines:
        y += 22
        subtotal += round(qty * unit, 2)
        t(50, y, desc); t(330, y, str(qty)); t(390, y, money(unit)); t(480, y, money(qty * unit))
    shown = printed_subtotal if printed_subtotal is not None else round(subtotal, 2)
    tax = round(shown * rate / 100, 2)
    y += 16
    page.draw_line((330, y), (545, y))
    for label, value in (("Subtotal", shown), (f"Tax ({rate}%)", tax), ("Total due", shown + tax)):
        y += 20
        font = "hebo" if label == "Total due" else "helv"
        t(390, y, label, 10, font); t(480, y, money(value), 10, font)
    t(50, 790, "Made-up invoice for a demo. Company names and addresses are not real.", 8)
    doc.set_metadata({"title": f"Invoice {number}", "author": "", "creator": "", "producer": ""})
    out = HERE / "samples" / f"{number}.pdf"
    out.parent.mkdir(exist_ok=True)
    doc.save(out, garbage=4, deflate=True)
    return out


for inv in INVOICES:
    write_pdf(*inv)
pdf = {p.name: base64.b64encode(p.read_bytes()).decode() for p in sorted((HERE / "samples").glob("*.pdf"))}
emails = [{"json": {"from": e["from"], "subject": e["subject"]},
           "files": {f"attachment_{k}": name for k, name in enumerate(e["files"])}} for e in EMAILS]

SAMPLE = ("// Two made-up mails shaped like the Gmail trigger's output: attachments arrive as attachment_0, attachment_1, ...\n"
          f"const PDF = {json.dumps(pdf)};\n"
          f"const MAILS = {json.dumps(emails)};\n"
          "return MAILS.map(({ json, files }) => ({ json, binary: Object.fromEntries(Object.entries(files).map(([key, fileName]) =>\n"
          "  [key, { data: PDF[fileName], mimeType: 'application/pdf', fileName, fileExtension: 'pdf' }])) }));")
SPLIT = """// A mail can carry several attachments. Keep the PDFs, one item each, with the mail it came from.
const out = [];
for (const { json, binary } of $input.all()) {
  for (const file of Object.values(binary ?? {})) {
    if (file.mimeType === 'application/pdf' || /\\.pdf$/i.test(file.fileName ?? '')) {
      out.push({ json: { from: json.from?.text ?? json.from ?? '', subject: json.subject ?? '', fileName: file.fileName }, binary: { data: file } });
    }
  }
}
return out;"""
READ = """// Pull the invoice fields and lines out of the PDF text, then check the arithmetic in whole cents.
const src = $('One item per PDF').all();
const num = s => Number(String(s ?? '').replace(/,/g, ''));
const cents = v => Math.round(v * 100);
const fmt = v => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
return $input.all().map(({ json }, i) => {
  const text = json.text ?? '';
  const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
  const field = re => (text.match(re) ?? [])[1];
  const items = lines
    .map(l => l.match(/^(.+?) (\\d+) ([\\d,]+\\.\\d{2}) ([\\d,]+\\.\\d{2})$/))  // description, qty, unit price, amount
    .filter(Boolean)
    .map(([, description, qty, unit, amount]) => ({ description, qty: num(qty), unitPrice: num(unit), amount: num(amount) }));
  const subtotal = num(field(/^Subtotal ([\\d,]+\\.\\d{2})$/m));
  const tax = num(field(/^Tax[^\\n]* ([\\d,]+\\.\\d{2})$/m));
  const total = num(field(/^Total due ([\\d,]+\\.\\d{2})$/m));
  const problems = [];
  if (!items.length) problems.push('no invoice lines found');
  for (const l of items) if (cents(l.qty * l.unitPrice) !== cents(l.amount)) problems.push(`${l.description}: ${l.qty} x ${fmt(l.unitPrice)} is not ${fmt(l.amount)}`);
  const lineSum = items.reduce((s, l) => s + cents(l.amount), 0);
  if (lineSum !== cents(subtotal)) problems.push(`lines add up to ${fmt(lineSum / 100)} but the subtotal says ${fmt(subtotal)}`);
  if (cents(subtotal) + cents(tax) !== cents(total)) problems.push(`subtotal + tax is ${fmt(subtotal + tax)} but the total says ${fmt(total)}`);
  return { json: {
    invoiceNo: field(/Invoice no: (\\S+)/) ?? '', date: field(/Date: (\\d{4}-\\d{2}-\\d{2})/) ?? '', vendor: lines[0] ?? '',
    subtotal, tax, total, items, ok: problems.length === 0, problems: problems.join('; '),
    fileName: src[i]?.json.fileName ?? '', from: src[i]?.json.from ?? '',
  } };
});"""
ROWS = """// One row per invoice line. The invoice details repeat on every row so the sheet sorts and filters cleanly.
return $input.all().flatMap(({ json: inv }) => inv.items.map((l, n) => ({ json: {
  'Invoice no': inv.invoiceNo, Date: inv.date, Vendor: inv.vendor, Line: n + 1, Description: l.description,
  Qty: l.qty, 'Unit price': l.unitPrice, Amount: l.amount, 'Invoice total': inv.total, 'Source file': inv.fileName,
} })));"""
PROBLEMS = """// One flat row per invoice that failed a check, for a person to look at.
return $input.all().map(({ json: inv }) => ({ json: {
  'Invoice no': inv.invoiceNo, Date: inv.date, Vendor: inv.vendor, 'Total due': inv.total, Problem: inv.problems,
  'Source file': inv.fileName, From: inv.from,
} }));"""

sheets = lambda tab: {"operation": "append", "documentId": {"__rl": True, "mode": "url", "value": ""},
                      "sheetName": {"__rl": True, "mode": "name", "value": tab},
                      "columns": {"mappingMode": "autoMapInputData", "value": {}}, "options": {}}
node = lambda nid, name, typ, ver, pos, params, **extra: {"parameters": params, "id": nid, "name": name, "type": "n8n-nodes-base." + typ,
                                                         "typeVersion": ver, "position": pos, **extra}
nodes = [
    node("i01", "Run demo", "manualTrigger", 1, [0, 0], {}),
    node("i02", "Sample invoice emails", "code", 2, [220, 0], {"jsCode": SAMPLE}),
    node("i03", "New invoice email", "gmailTrigger", 1.2, [220, 200],
         {"pollTimes": {"item": [{"mode": "everyMinute"}]}, "simple": False,
          "filters": {"q": "has:attachment filename:pdf"}, "options": {"downloadAttachments": True}}, disabled=True),
    node("i04", "One item per PDF", "code", 2, [440, 100], {"jsCode": SPLIT}),
    node("i05", "PDF to text", "extractFromFile", 1, [660, 100], {"operation": "pdf", "options": {}}),
    node("i06", "Read invoice", "code", 2, [880, 100], {"jsCode": READ}),
    node("i07", "Sums check out?", "if", 2, [1100, 100], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                       "conditions": [{"id": "c-ok", "leftValue": "={{ $json.ok }}", "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"}, "options": {}}),
    node("i08", "One row per line", "code", 2, [1320, 0], {"jsCode": ROWS}),
    node("i09", "Excel file", "convertToFile", 1.1, [1540, -100], {"operation": "xlsx", "options": {"fileName": "invoices.xlsx", "sheetName": "Invoice lines"}}),
    node("i10", "Sheets: Invoice lines", "googleSheets", 4.5, [1540, 100], sheets("Invoice lines"), disabled=True),
    node("i11", "Problem rows", "code", 2, [1320, 250], {"jsCode": PROBLEMS}),
    node("i12", "Sheets: Check by hand", "googleSheets", 4.5, [1540, 250], sheets("Check by hand"), disabled=True),
]
link = lambda *names: [{"node": n, "type": "main", "index": 0} for n in names]
connections = {
    "Run demo": {"main": [link("Sample invoice emails")]},
    "Sample invoice emails": {"main": [link("One item per PDF")]},
    "New invoice email": {"main": [link("One item per PDF")]},
    "One item per PDF": {"main": [link("PDF to text")]},
    "PDF to text": {"main": [link("Read invoice")]},
    "Read invoice": {"main": [link("Sums check out?")]},
    "Sums check out?": {"main": [link("One row per line"), link("Problem rows")]},
    "One row per line": {"main": [link("Excel file", "Sheets: Invoice lines")]},
    "Problem rows": {"main": [link("Sheets: Check by hand")]},
}
wf = {"id": "invoicePdfDemo01", "name": "Invoice PDFs from email to a spreadsheet, with a sum check",
      "nodes": nodes, "connections": connections, "active": False, "settings": {"executionOrder": "v1"}}
(HERE / "workflow.json").write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("samples:", ", ".join(pdf), "| workflow.json", len(nodes), "nodes")
