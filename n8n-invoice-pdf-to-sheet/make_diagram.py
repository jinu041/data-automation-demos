"""Draw workflow.json as diagram.png (node positions come from the workflow itself)."""
import json, pathlib
from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
wf = json.loads((HERE / "workflow.json").read_text(encoding="utf-8"))
bold = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 19)
small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 15)
W, H, SX, M = 232, 66, 1.18, 60  # box size, horizontal stretch, margin
KIND = {  # type -> (fill, second line)
    "n8n-nodes-base.manualTrigger": ("#dff3e4", "Manual trigger"),
    "n8n-nodes-base.gmailTrigger": ("#f1f1f1", "Gmail trigger, needs login"),
    "n8n-nodes-base.code": ("#e3ecfb", "Code (JavaScript)"),
    "n8n-nodes-base.extractFromFile": ("#efe6fb", "Extract from file (PDF)"),
    "n8n-nodes-base.if": ("#fdf0d5", "IF"),
    "n8n-nodes-base.convertToFile": ("#e2f4f1", "Convert to file (XLSX)"),
    "n8n-nodes-base.googleSheets": ("#f1f1f1", "Google Sheets, needs login"),
}
x0 = min(n["position"][0] for n in wf["nodes"])
y0 = min(n["position"][1] for n in wf["nodes"])
pos = {n["name"]: (M + (n["position"][0] - x0) * SX, 70 + (n["position"][1] - y0) * 0.95) for n in wf["nodes"]}
is_if = {n["name"] for n in wf["nodes"] if n["type"] == "n8n-nodes-base.if"}
NW = int(max(x for x, _ in pos.values()) + W + M)
NH = int(max(y for _, y in pos.values()) + H + 70)
img = Image.new("RGB", (NW, NH), "white")
d = ImageDraw.Draw(img)
d.text((M, 18), wf["name"], font=bold, fill="#222")

for src, outs in wf["connections"].items():
    for k, branch in enumerate(outs["main"]):
        for c in branch:
            (x1, y1), (x2, y2) = pos[src], pos[c["node"]]
            a, b = (x1 + W, y1 + H / 2), (x2, y2 + H / 2)
            mid = (a[0] + b[0]) / 2
            d.line([a, (mid, a[1]), (mid, b[1]), b], fill="#8a94a6", width=3)
            d.polygon([b, (b[0] - 11, b[1] - 6), (b[0] - 11, b[1] + 6)], fill="#8a94a6")
            if src in is_if:
                d.text((b[0] - 42, b[1] - 24), "yes" if k == 0 else "no", font=small, fill="#555")

for n in wf["nodes"]:
    x, y = pos[n["name"]]
    fill, kind = KIND[n["type"]]
    off = n.get("disabled", False)
    d.rounded_rectangle([x, y, x + W, y + H], 12, fill=fill, outline="#9aa3b2" if off else "#4a5568", width=2)
    d.text((x + 12, y + 9), n["name"], font=bold, fill="#777" if off else "#1a202c")
    d.text((x + 12, y + 38), kind, font=small, fill="#555")
    assert d.textlength(n["name"], font=bold) < W - 16 and d.textlength(kind, font=small) < W - 16, n["name"]

d.text((M, NH - 34), "Grey boxes are off in the demo: connect your Gmail and Google Sheets accounts in n8n, then switch them on.", font=small, fill="#555")
img.save(HERE / "diagram.png", optimize=True)
print("diagram.png", img.size)
