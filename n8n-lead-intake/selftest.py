"""Import workflow.json into n8n, run it from the command line and check the result.

Needs n8n (tested with 2.49.6). Set N8N_CMD if `npx n8n` is not how you start it, e.g.
  N8N_CMD="pwsh -NoProfile -File C:/tools/n8n/run_n8n.ps1" python selftest.py
"""
import json, os, pathlib, shlex, subprocess

HERE = pathlib.Path(__file__).resolve().parent
N8N = shlex.split(os.environ.get("N8N_CMD", "npx n8n"), posix=os.name != "nt")


def n8n(*args):
    out = subprocess.run(N8N + list(args), capture_output=True, text=True, encoding="utf-8", shell=os.name == "nt")
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


n8n("import:workflow", "--input=" + str(HERE / "workflow.json"))
raw = n8n("execute", "--id=leadIntakeDemo01", "--rawOutput")
run = json.loads(raw[raw.index("{"):])
assert run["status"] == "success", run["status"]
nodes = run["data"]["resultData"]["runData"]
first = lambda name, out=0: [i["json"] for i in nodes[name][0]["data"]["main"][out]]

summary = first("Run summary")[0]
assert (summary["kept"], summary["hot"], summary["warm"], summary["cold"]) == (5, 2, 1, 2), summary
rejected = {l["name"]: l["issues"] for l in first("Usable?", 1)}
assert rejected == {"Lee": "no email or phone", "Aisha Khan": "email looks wrong"}, rejected
scored = {l["name"]: (l["tier"], l["score"]) for l in first("Score")}
assert scored["Maria Gomez"] == ("cold", 15), "'Not urgent' must not count as urgent"
assert scored["Chen Wei"] == ("hot", 75) and scored["Jane Cooper"] == ("hot", 80), scored
print("selftest ok: 8 leads in, 2 sent to 'Check by hand', 1 duplicate dropped, 5 scored (2 hot, 1 warm, 2 cold)")
