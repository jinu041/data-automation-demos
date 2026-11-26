"""Import workflow.json into n8n, run it from the command line and check the result.

Needs n8n (tested with 2.49.6). Set N8N_CMD if `npx n8n` is not how you start it, e.g. N8N_CMD=n8n
"""
import json, os, pathlib, shlex, shutil, subprocess, tempfile

HERE = pathlib.Path(__file__).resolve().parent
N8N = shlex.split(os.environ.get("N8N_CMD", "npx n8n"), posix=os.name != "nt")


def n8n(*args):
    out = subprocess.run(N8N + list(args), cwd=HERE, capture_output=True, text=True, encoding="utf-8", shell=os.name == "nt")
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


wf = json.loads((HERE / "workflow.json").read_text(encoding="utf-8"))
os.environ["N8N_USER_FOLDER"] = tmp = tempfile.mkdtemp(prefix="n8n-selftest-")  # throwaway: your own n8n stays untouched
try:
    n8n("import:workflow", "--input=workflow.json")  # relative, because a PowerShell wrapper splits "--input=C:\..." at the colon
    raw = n8n("execute", "--id=" + wf["id"], "--rawOutput")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
run = json.loads(raw[raw.index("{"):])
assert run["status"] == "success", run["status"]
nodes = run["data"]["resultData"]["runData"]
expected = {n["name"] for n in wf["nodes"] if n["type"] != "n8n-nodes-base.gmailTrigger"}
assert set(nodes) == expected, ("n8n ran a different copy of the workflow", sorted(nodes))
first = lambda name, out=0: [i["json"] for i in nodes[name][0]["data"]["main"][out]]

pdfs = first("One item per PDF")
assert sorted(p["fileName"] for p in pdfs) == ["HP-2207.pdf", "INV-1041.pdf", "PC-3315.pdf"], pdfs
invoices = {i["invoiceNo"]: i for i in first("Read invoice")}
assert (invoices["INV-1041"]["total"], invoices["HP-2207"]["total"], invoices["PC-3315"]["total"]) == (308.77, 226.8, 92.0), invoices
assert [i["invoiceNo"] for i in first("Sums check out?")] == ["INV-1041", "HP-2207"]
bad = first("Problem rows")
assert [(b["Invoice no"], b["Problem"]) for b in bad] == [("PC-3315", "lines add up to 82.00 but the subtotal says 92.00")], bad
rows = first("One row per line")
assert len(rows) == 5 and round(sum(r["Amount"] for r in rows), 2) == 490.7, rows
assert rows[3] == {"Invoice no": "HP-2207", "Date": "2026-11-10", "Vendor": "Harbor Print Co.", "Line": 1,
                   "Description": "Business cards, 500 pcs", "Qty": 2, "Unit price": 45, "Amount": 90,
                   "Invoice total": 226.8, "Source file": "HP-2207.pdf"}, rows[3]
xlsx = nodes["Excel file"][0]["data"]["main"][0]
assert len(xlsx) == 1 and xlsx[0]["binary"]["data"]["fileName"] == "invoices.xlsx", xlsx
print("selftest ok: 2 mails, 3 PDFs read, 2 invoices pass (5 lines, 490.70 into invoices.xlsx), "
      "PC-3315 sent to 'Check by hand': " + bad[0]["Problem"])
