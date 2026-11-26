"""Write the semantic model and the report page of the Power BI demo into a PBIP project folder.

    python build_pbip.py <project folder> <path to sales.csv>

The folder must hold a project that Power BI Desktop saved once (SalesDemo.pbip, SalesDemo.Report,
SalesDemo.SemanticModel). This script replaces the table, measures and report page with the ones below;
Power BI Desktop then opens the project, refreshes the data and saves it in its own formatting.
"""
import hashlib, json, shutil, sys, uuid
from pathlib import Path

T = "sales"
COLUMNS = [  # name, TMDL data type, Power Query type, format string
    ("OrderID", "string", "type text", None),
    ("OrderDate", "dateTime", "type date", "yyyy-mm-dd"),
    ("Month", "dateTime", "type date", "mmm yyyy"),
    ("Region", "string", "type text", None),
    ("Channel", "string", "type text", None),
    ("Category", "string", "type text", None),
    ("Product", "string", "type text", None),
    ("Units", "int64", "Int64.Type", "#,0"),
    ("UnitPrice", "double", "type number", "\\$#,0.00"),
    ("UnitCost", "double", "type number", "\\$#,0.00"),
    ("Revenue", "double", "type number", "\\$#,0.00"),
    ("Cost", "double", "type number", "\\$#,0.00"),
]
MEASURES = [  # name, DAX, format string
    ("Total Revenue", f"SUM({T}[Revenue])", "\\$#,0"),
    ("Gross Margin %", f"DIVIDE([Total Revenue] - SUM({T}[Cost]), [Total Revenue])", "0.0%"),
    ("Orders", f"DISTINCTCOUNT({T}[OrderID])", "#,0"),
    ("Avg Order Value", "DIVIDE([Total Revenue], [Orders])", "\\$#,0.00"),
]
SUMMED = {"Units", "Revenue", "Cost"}
# A text label so the month axis reads "Jan 2025" whatever the PC's regional settings are; sorted by Month.
LABEL = ("MonthLabel", 'Date.ToText([Month], [Format="MMM yyyy", Culture="en-US"])', "Month")


def tag(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "powerbi-sales-dashboard/" + name))


def q(name):  # TMDL quotes names with spaces or symbols
    return name if name.isidentifier() else "'" + name.replace("'", "''") + "'"


def table_tmdl():
    out = [f"table {T}", f"\tlineageTag: {tag(T)}", ""]
    for name, dax, fmt in MEASURES:
        out += [f"\tmeasure {q(name)} = {dax}", f"\t\tformatString: {fmt}", f"\t\tlineageTag: {tag('m/' + name)}", ""]
    for name, dtype, _, fmt in COLUMNS + [(LABEL[0], "string", None, None)]:
        out += [f"\tcolumn {q(name)}", f"\t\tdataType: {dtype}"]
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out += [f"\t\tlineageTag: {tag('c/' + name)}", f"\t\tsummarizeBy: {'sum' if name in SUMMED else 'none'}",
                f"\t\tsourceColumn: {name}"]
        if name == LABEL[0]:
            out.append(f"\t\tsortByColumn: {LABEL[2]}")
        out += ["", "\t\tannotation SummarizationSetBy = Automatic", ""]
    types = ", ".join('{"%s", %s}' % (n, pq) for n, _, pq, _ in COLUMNS)
    out += [
        f"\tpartition {T} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
        f'\t\t\t\t    Source = Csv.Document(File.Contents(DataFile), [Delimiter=",", Columns={len(COLUMNS)}, '
        'Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        "\t\t\t\t    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),",
        f"\t\t\t\t    Typed = Table.TransformColumnTypes(Headers, {{{types}}}),",
        f'\t\t\t\t    Labeled = Table.AddColumn(Typed, "{LABEL[0]}", each {LABEL[1]}, type text)',
        "\t\t\t\tin", "\t\t\t\t    Labeled", "", "\tannotation PBI_ResultType = Table", "",
    ]
    return "\n".join(out)


def expressions_tmdl(csv_path):
    path = str(csv_path).replace('"', '""')
    return "\n".join([
        f'expression DataFile = "{path}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]',
        f"\tlineageTag: {tag('DataFile')}", "", "\tannotation PBI_ResultType = Text", "",
    ])


MODEL_TMDL = f"""model Model
\tculture: en-US
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tsourceQueryCulture: en-US
\tvalueFilterBehavior: independent
\tdataAccessOptions
\t\tlegacyRedirects
\t\treturnErrorValuesAsNull

annotation __PBI_TimeIntelligenceEnabled = 0

annotation PBI_QueryOrder = ["DataFile","{T}"]

annotation PBI_ProTooling = ["DevMode"]

ref table {T}

ref cultureInfo en-US
"""

# ---------- report ----------
VC = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.15.0/schema.json"


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def field(kind, prop):
    return {kind: {"Expression": {"SourceRef": {"Entity": T}}, "Property": prop}}


def proj(kind, prop):
    return {"field": field(kind, prop), "queryRef": f"{T}.{prop}", "nativeQueryRef": prop}


def vid(label):
    return hashlib.md5(label.encode()).hexdigest()[:20]


def visual(label, vtype, box, roles=None, title=None, objects=None, sort=None):
    x, y, w, h = box
    v = {"visualType": vtype}
    if roles:
        v["query"] = {"queryState": {r: {"projections": [proj(k, p) for k, p in ps]} for r, ps in roles.items()}}
        if sort:
            kind, prop, direction = sort
            v["query"]["sortDefinition"] = {"sort": [{"field": field(kind, prop), "direction": direction}], "isDefaultSort": True}
    if objects:
        v["objects"] = objects
    if title:
        v["visualContainerObjects"] = {"title": [{"properties": {"show": lit("true"), "text": lit(f"'{title}'")}}],
                                       "subTitle": [{"properties": {"show": lit("false")}}]}
    v["drillFilterOtherVisuals"] = True
    return vid(label), {"$schema": VC, "name": vid(label), "position": {"x": x, "y": y, "z": 0, "height": h, "width": w, "tabOrder": 0}, "visual": v}


M, C = "Measure", "Column"
NO_UNITS = {"labels": [{"properties": {"labelDisplayUnits": lit("1D")}}]}  # show $569,005, not $569K
TITLE = {"general": [{"properties": {"paragraphs": [
    {"textRuns": [{"value": "Coffee roaster sales dashboard, 2025", "textStyle": {"fontWeight": "bold", "fontSize": "24pt"}}]},
    {"textRuns": [{"value": "Fictional demo data: 3,021 order lines from a made-up roaster selling online, wholesale and to cafes.",
                   "textStyle": {"fontSize": "12pt"}}]},
]}}]}
VISUALS = [
    visual("title", "textbox", (40, 16, 1300, 90), objects=TITLE),
    visual("slicer-region", "slicer", (1480, 24, 400, 80), {"Values": [(C, "Region")]},
           objects={"data": [{"properties": {"mode": lit("'Dropdown'")}}]}),
    visual("card-revenue", "card", (40, 120, 440, 150), {"Values": [(M, "Total Revenue")]}, objects=NO_UNITS),
    visual("card-margin", "card", (500, 120, 440, 150), {"Values": [(M, "Gross Margin %")]}, objects=NO_UNITS),
    visual("card-orders", "card", (960, 120, 440, 150), {"Values": [(M, "Orders")]}, objects=NO_UNITS),
    visual("card-aov", "card", (1420, 120, 460, 150), {"Values": [(M, "Avg Order Value")]}, objects=NO_UNITS),
    visual("line-month", "lineChart", (40, 290, 1150, 380), {"Category": [(C, "MonthLabel")], "Y": [(M, "Total Revenue")]},
           title="Revenue by month", sort=(C, "MonthLabel", "Ascending")),
    visual("donut-channel", "donutChart", (1210, 290, 670, 380), {"Category": [(C, "Channel")], "Y": [(M, "Total Revenue")]},
           title="Revenue by channel"),
    visual("bar-product", "clusteredBarChart", (40, 690, 1150, 370), {"Category": [(C, "Product")], "Y": [(M, "Total Revenue")]},
           title="Revenue by product", sort=(M, "Total Revenue", "Descending")),
    visual("table-region", "tableEx", (1210, 690, 670, 370),
           {"Values": [(C, "Region"), (M, "Total Revenue"), (M, "Gross Margin %"), (M, "Orders")]},
           title="By region", sort=(M, "Total Revenue", "Descending")),
]


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:  # PBIP files are UTF-8 without BOM, CRLF
        f.write(text)


def main(project, csv_path):
    project = Path(project)
    sm = next(project.glob("*.SemanticModel"))
    rp = next(project.glob("*.Report"))
    d = sm / "definition"
    for f in list((d / "tables").glob("*.tmdl")) + list((d / "cultures").glob("*.tmdl")) + [d / "relationships.tmdl"]:
        f.unlink(missing_ok=True)  # drop Desktop's auto date tables and the Korean culture
    write(d / "tables" / f"{T}.tmdl", table_tmdl())
    write(d / "expressions.tmdl", expressions_tmdl(csv_path))
    write(d / "model.tmdl", MODEL_TMDL)
    write(d / "cultures" / "en-US.tmdl", "cultureInfo en-US\n")
    (sm / "diagramLayout.json").unlink(missing_ok=True)

    pages = rp / "definition" / "pages"
    page_id = json.loads((pages / "pages.json").read_text(encoding="utf-8"))["pageOrder"][0]
    page = json.loads((pages / page_id / "page.json").read_text(encoding="utf-8"))
    page["displayName"] = "Sales overview"
    write(pages / page_id / "page.json", json.dumps(page, indent=2, ensure_ascii=False) + "\n")
    shutil.rmtree(pages / page_id / "visuals", ignore_errors=True)
    for name, body in VISUALS:
        write(pages / page_id / "visuals" / name / "visual.json", json.dumps(body, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(MEASURES)} measures, {len(COLUMNS)} columns and {len(VISUALS)} visuals into {project}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
