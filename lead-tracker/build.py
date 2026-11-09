# Lead tracker for a small service business (Excel + Google Sheets, formulas only, no macros).
# Builds lead-tracker.xlsx (empty template) and lead-tracker-sample.xlsx (made-up leads).
# Run: uv run --no-project --with openpyxl python build.py
import datetime as dt
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).parent
FIRST, LAST = 2, 501  # 500 lead rows
SOURCES = ["Website form", "Phone call", "Referral", "Google", "Facebook", "Walk-in", "Other"]
STATUSES = ["New", "Contacted", "Quote sent", "Won", "Lost"]
HEAD = ["Lead ID", "Date added", "Contact name", "Company", "Email", "Source", "Service", "Est. value",
        "Status", "Last contact", "Next follow-up", "Follow-up flag", "Calendar", "Notes"]
WIDTH = [9, 12, 18, 22, 26, 14, 24, 11, 12, 12, 14, 14, 22, 30]
DARK, LIGHT = "2F4858", "EEF2F5"
thin = Side(style="thin", color="D0D5DD")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)


def fill(c):  # conditional formats read the background from end_color, so set both
    return PatternFill("solid", start_color=c, end_color=c)


# Made-up leads for the sample file. Dates are relative to the build date so the flags look alive.
def sample(today):
    d = lambda n: today + dt.timedelta(days=n)
    return [
        ("Alex Morgan", "Morgan Bakery", "Website form", "Kitchen plumbing repair", 450, "Quote sent", d(-12), d(-5), d(-2), "Waiting on landlord approval"),
        ("Priya Shah", "Shah Dental", "Referral", "Bathroom remodel", 6800, "Contacted", d(-10), d(-6), d(1), "Wants two options"),
        ("Tom Becker", "", "Phone call", "Water heater install", 1900, "Won", d(-25), d(-20), None, "Install booked"),
        ("Grace Lee", "Lee Florist", "Google", "Leak inspection", 250, "New", d(-1), None, d(0), ""),
        ("Daniel Ortiz", "Ortiz Auto", "Facebook", "Shop sink + drain", 1200, "Quote sent", d(-8), d(-4), d(3), "Asked for a discount"),
        ("Hannah Kim", "", "Website form", "Toilet replacement", 600, "Lost", d(-30), d(-21), None, "Went with a cheaper quote"),
        ("Marcus Hill", "Hill Cafe", "Referral", "Grease trap service", 900, "Contacted", d(-6), d(-3), d(5), ""),
        ("Sofia Rossi", "", "Walk-in", "Shower valve repair", 380, "New", d(-2), None, d(-1), "Call after 5 pm"),
        ("Ken Watanabe", "Watanabe Studio", "Google", "Office restroom refit", 4200, "Quote sent", d(-14), d(-9), d(-3), ""),
        ("Laura Chen", "", "Phone call", "Burst pipe (urgent)", 700, "Won", d(-5), d(-5), None, "Done same day"),
        ("Omar Haddad", "Haddad Market", "Other", "Backflow test", 300, "Contacted", d(-4), d(-2), d(10), ""),
        ("Emma Novak", "", "Website form", "Kitchen remodel", 9500, "New", d(0), None, d(2), "Send portfolio photos"),
    ]


def build(path, leads):
    wb = Workbook()
    how = wb.active
    how.title = "How to use"
    ws = wb.create_sheet("Leads")
    dash = wb.create_sheet("Dashboard")
    lists = wb.create_sheet("Lists")

    # Lists (drop-down sources)
    lists.append(["Sources", "Statuses"])
    for i in range(max(len(SOURCES), len(STATUSES))):
        lists.append([SOURCES[i] if i < len(SOURCES) else None, STATUSES[i] if i < len(STATUSES) else None])
    for c in lists[1]:
        c.font = Font(bold=True)

    # Leads
    ws.append(HEAD)
    for c, w in zip(ws[1], WIDTH):
        c.font, c.fill, c.alignment = Font(bold=True, color="FFFFFF"), fill(DARK), Alignment(vertical="center")
        ws.column_dimensions[c.column_letter].width = w
    ws.row_dimensions[1].height = 22
    for r in range(FIRST, LAST + 1):
        ws[f"A{r}"] = f'=IF(C{r}="","","L-"&TEXT(ROW()-1,"000"))'
        ws[f"L{r}"] = (f'=IF(OR(C{r}="",K{r}="",I{r}="Won",I{r}="Lost"),"",'
                       f'IF(K{r}<TODAY(),"Overdue",IF(K{r}<=TODAY()+7,"This week","")))')
        # Google Calendar all-day event link. SUBSTITUTE instead of ENCODEURL so it also works in Excel for Mac/web.
        text = f'SUBSTITUTE(SUBSTITUTE(SUBSTITUTE("Follow up: "&C{r}&IF(D{r}=""," "," - "&D{r})," ","%20"),"&","%26"),"#","%23")'
        ws[f"M{r}"] = (f'=IF(OR(C{r}="",K{r}=""),"",HYPERLINK("https://calendar.google.com/calendar/render?action=TEMPLATE&text="'
                       f'&{text}&"&dates="&TEXT(K{r},"yyyymmdd")&"/"&TEXT(K{r}+1,"yyyymmdd"),"Add to Google Calendar"))')
        for col in "BJK":
            ws[f"{col}{r}"].number_format = "yyyy-mm-dd"
        ws[f"H{r}"].number_format = '"$"#,##0'
        for col in "ABCDEFGHIJKLMN":
            ws[f"{col}{r}"].border = BOX
    for r, (name, co, src, svc, val, st, added, last, nxt, note) in enumerate(leads, FIRST):
        email = name.lower().replace(" ", ".") + "@example.com"
        for col, v in zip("BCDEFGHIJKN", (added, name, co or None, email, src, svc, val, st, last, nxt, note or None)):
            ws[f"{col}{r}"] = v
    rng = f"A{FIRST}:N{LAST}"
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'$I{FIRST}="Won"'], fill=fill("E3F4E8")))
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'$I{FIRST}="Lost"'], font=Font(color="9AA3AD")))
    ws.conditional_formatting.add(f"L{FIRST}:L{LAST}", FormulaRule(formula=[f'$L{FIRST}="Overdue"'], fill=fill("F8D7DA"), font=Font(bold=True, color="9C1C17")))
    ws.conditional_formatting.add(f"L{FIRST}:L{LAST}", FormulaRule(formula=[f'$L{FIRST}="This week"'], fill=fill("FFF3CD")))
    dv_src = DataValidation(type="list", formula1=f"=Lists!$A$2:$A${len(SOURCES) + 1}", allow_blank=True)
    dv_st = DataValidation(type="list", formula1=f"=Lists!$B$2:$B${len(STATUSES) + 1}", allow_blank=True)
    dv_date = DataValidation(type="date", operator="greaterThan", formula1="DATE(2000,1,1)", allow_blank=True,
                             error="Please enter a date like 2026-11-10.", showErrorMessage=True)
    for dv, ref in ((dv_src, f"F{FIRST}:F{LAST}"), (dv_st, f"I{FIRST}:I{LAST}"), (dv_date, f"B{FIRST}:B{LAST} J{FIRST}:K{LAST}")):
        ws.add_data_validation(dv)
        for part in ref.split():
            dv.add(part)
    for col in "CDEFGHIJKN":  # input cells
        for r in range(FIRST, LAST + 1):
            ws[f"{col}{r}"].fill = fill("FFFDF5")
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:N{LAST}"

    # Dashboard
    L = lambda col: f"Leads!${col}${FIRST}:${col}${LAST}"
    dash.column_dimensions["A"].width = 30
    dash.column_dimensions["B"].width = 16
    dash.column_dimensions["D"].width = 18
    dash.column_dimensions["E"].width = 10
    dash.column_dimensions["F"].width = 10
    dash["A1"] = "Lead dashboard"
    dash["A1"].font = Font(bold=True, size=16, color=DARK)
    dash["A2"] = '="Updated "&TEXT(TODAY(),"yyyy-mm-dd")'
    dash["A2"].font = Font(color="667085")
    kpis = [
        ("Total leads", f'=COUNTIF({L("C")},"?*")', "0"),
        ("New this month", f'=COUNTIFS({L("B")},">="&DATE(YEAR(TODAY()),MONTH(TODAY()),1),{L("B")},"<"&EDATE(DATE(YEAR(TODAY()),MONTH(TODAY()),1),1))', "0"),
        ("Open pipeline value", f'=SUMIFS({L("H")},{L("C")},"?*",{L("I")},"<>Won",{L("I")},"<>Lost")', '"$"#,##0'),
        ("Won value", f'=SUMIFS({L("H")},{L("I")},"Won")', '"$"#,##0'),
        ("Win rate (won / closed)", f'=IFERROR(COUNTIF({L("I")},"Won")/(COUNTIF({L("I")},"Won")+COUNTIF({L("I")},"Lost")),"")', "0%"),
        ("Follow-ups overdue", f'=COUNTIF({L("L")},"Overdue")', "0"),
        ("Follow-ups this week", f'=COUNTIF({L("L")},"This week")', "0"),
    ]
    for i, (label, f, fmt) in enumerate(kpis, 4):
        dash[f"A{i}"], dash[f"B{i}"] = label, f
        dash[f"B{i}"].number_format = fmt
        dash[f"B{i}"].font = Font(bold=True, size=13)
        for c in (dash[f"A{i}"], dash[f"B{i}"]):
            c.border, c.fill = BOX, fill(LIGHT)
    dash["B9"].font = Font(bold=True, size=13, color="9C1C17")
    dash["D3"], dash["E3"], dash["F3"] = "By status", "Leads", "Value"
    for i, s in enumerate(STATUSES, 4):
        dash[f"D{i}"], dash[f"E{i}"] = s, f'=COUNTIF({L("I")},D{i})'
        dash[f"F{i}"] = f'=SUMIFS({L("H")},{L("I")},D{i})'
        dash[f"F{i}"].number_format = '"$"#,##0'
    dash["D11"], dash["E11"], dash["F11"] = "By source", "Leads", "Won"
    for i, s in enumerate(SOURCES, 12):
        dash[f"D{i}"], dash[f"E{i}"] = s, f'=COUNTIF({L("F")},D{i})'
        dash[f"F{i}"] = f'=COUNTIFS({L("F")},D{i},{L("I")},"Won")'
    for ref in ("D3", "E3", "F3", "D11", "E11", "F11"):
        dash[ref].font, dash[ref].fill = Font(bold=True, color="FFFFFF"), fill(DARK)

    # How to use
    how.column_dimensions["A"].width = 100
    for i, line in enumerate([
        "Lead tracker: how to use",
        "1. Leads tab: add one row per enquiry. Fill the light-yellow cells; Lead ID, Follow-up flag and Calendar fill in by themselves.",
        "2. Status and Source are drop-downs (edit the choices on the Lists tab). Dates use the format 2026-11-10.",
        "3. Next follow-up: the flag turns red (Overdue) or yellow (This week). Won and Lost leads are not flagged.",
        "4. Calendar: click 'Add to Google Calendar' to open a ready-made all-day reminder for that follow-up date.",
        "5. Dashboard tab: totals, open pipeline value, win rate and counts by status and source update automatically.",
        "Formulas only, no macros. Works in Excel and Google Sheets (File > Import or open the .xlsx from Google Drive).",
        "Sample data in lead-tracker-sample.xlsx is made up. Names and emails use example.com.",
    ], 1):
        how[f"A{i}"] = line
        how[f"A{i}"].alignment = Alignment(wrap_text=True, vertical="top")
    how["A1"].font = Font(bold=True, size=14, color=DARK)
    wb.active = 1
    wb.properties.creator = ""
    wb.save(path)


if __name__ == "__main__":
    today = dt.date.today()
    leads = sample(today)
    build(HERE / "lead-tracker.xlsx", [])
    build(HERE / "lead-tracker-sample.xlsx", leads)
    # Expected dashboard values for check.py (computed in Python, independent of the formulas)
    open_ = [x for x in leads if x[5] not in ("Won", "Lost")]
    flag =lambda x: "" if x[5] in ("Won", "Lost") or x[8] is None else ("Overdue" if x[8] < today else ("This week" if x[8] <= today + dt.timedelta(days=7) else ""))
    month_start = today.replace(day=1)
    exp = {
        "total": len(leads),
        "new_this_month": sum(1 for x in leads if x[6] >= month_start),
        "open_value": sum(x[4] for x in open_),
        "won_value": sum(x[4] for x in leads if x[5] == "Won"),
        "win_rate": sum(x[5] == "Won" for x in leads) / sum(x[5] in ("Won", "Lost") for x in leads),
        "overdue": sum(flag(x) == "Overdue" for x in leads),
        "this_week": sum(flag(x) == "This week" for x in leads),
        "date": today.isoformat(),
    }
    (HERE / "expected.json").write_text(json.dumps(exp, indent=1), encoding="utf-8")
    print("built", exp)
