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
expected = {n["name"] for n in wf["nodes"] if n["type"] != "n8n-nodes-base.webhook"}
assert set(nodes) == expected, ("n8n ran a different copy of the workflow", sorted(nodes))
first = lambda name, out=0: [i["json"] for i in nodes[name][0]["data"]["main"][out]]

summary = first("Run summary")[0]
assert (summary["kept"], summary["hot"], summary["warm"], summary["cold"]) == (5, 2, 1, 2), summary
rejected = {l["name"]: l["issues"] for l in first("Usable?", 1)}
assert rejected == {"Lee": "no email or phone", "Aisha Khan": "email looks wrong"}, rejected
scored = {l["name"]: (l["tier"], l["score"]) for l in first("Score")}
assert scored["Maria Gomez"] == ("cold", 15), "'Not urgent' must not count as urgent"
assert scored["Chen Wei"] == ("hot", 75) and scored["Jane Cooper"] == ("hot", 80), scored
assert "budget $2,000" in next(l for l in summary["leads"] if "Chen Wei" in l), summary["leads"]
print("selftest ok: 8 leads in, 2 sent to 'Check by hand', 1 duplicate dropped, 5 scored (2 hot, 1 warm, 2 cold)")
