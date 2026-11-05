"""Create a sample Excel workbook with openpyxl.

Sheets:
  데이터  Monthly sales table (header style, filter, frozen header, number format)
  요약    Formulas (total / average / max / min / best month) and a bar chart

Usage:
  python scripts/create_xlsx.py [-o output/sample.xlsx] [--color blue]

--color accepts a name (red, blue, green, 빨강, 파랑 ...) or HEX (#1F4E79).
"""
import argparse
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FONT = "맑은 고딕"
DEFAULT_COLOR = "1F4E79"
NAMED = {
    "red": "C00000", "빨강": "C00000", "blue": "2E75B6", "파랑": "2E75B6",
    "navy": "1F3864", "green": "548235", "초록": "548235", "orange": "ED7D31",
    "주황": "ED7D31", "purple": "7030A0", "보라": "7030A0", "gray": "595959",
    "회색": "595959", "black": "000000", "검정": "000000",
}

DATA = [
    ("월", "제품A", "제품B", "제품C"),
    ("1월", 1200000, 850000, 430000),
    ("2월", 1350000, 910000, 470000),
    ("3월", 1500000, 780000, 520000),
    ("4월", 1420000, 960000, 610000),
    ("5월", 1680000, 1020000, 580000),
    ("6월", 1750000, 1110000, 690000),
]


def parse_color(value):
    v = str(value).strip().lower().replace(" ", "")
    m = re.fullmatch(r"#?([0-9a-f]{6})", v)
    if m:
        return m.group(1).upper()
    key = v[:-1] if v.endswith("색") and v not in NAMED else v
    if key in NAMED:
        return NAMED[key]
    sys.exit(f"unknown color: {value!r}. Use a HEX value like #1F4E79 or a name such as blue, 빨강.")


def text_on(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return "000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 160 else "FFFFFF"


def build(color):
    wb = Workbook()
    thin = Side(style="thin", color=color)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor=color)
    head_font = Font(name=FONT, bold=True, color=text_on(color))
    body_font = Font(name=FONT)

    # ---- 데이터 sheet ----
    ws = wb.active
    ws.title = "데이터"
    for r, row in enumerate(DATA, start=1):
        for c, value in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.border = border
            if r == 1:
                cell.font, cell.fill = head_font, head_fill
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.font = body_font
                if c > 1:
                    cell.number_format = "#,##0"
    last = len(DATA)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(DATA[0]))}{last}"
    for c in range(1, len(DATA[0]) + 1):
        ws.column_dimensions[get_column_letter(c)].width = 14
    ws.row_dimensions[1].height = 24

    # ---- 요약 sheet ----
    sm = wb.create_sheet("요약")
    sm["A1"], sm["B1"] = "항목", "값"
    for cell in (sm["A1"], sm["B1"]):
        cell.font, cell.fill = head_font, head_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = border
    # Row total per month goes in 데이터!E so the best month can be looked up.
    ws["E1"] = "합계"
    ws["E1"].font, ws["E1"].fill = head_font, head_fill
    ws["E1"].alignment = Alignment(horizontal="center", vertical="center")
    ws["E1"].border = border
    ws.column_dimensions["E"].width = 14
    for r in range(2, last + 1):
        ws[f"E{r}"] = f"=SUM(B{r}:D{r})"
        ws[f"E{r}"].number_format = "#,##0"
        ws[f"E{r}"].font = body_font
        ws[f"E{r}"].border = border
    ws.auto_filter.ref = f"A1:E{last}"

    rows = [
        ("전체 매출 합계", f"=SUM(데이터!E2:E{last})", "#,##0"),
        ("월 평균 매출", f"=AVERAGE(데이터!E2:E{last})", "#,##0"),
        ("최고 월 매출", f"=MAX(데이터!E2:E{last})", "#,##0"),
        ("최저 월 매출", f"=MIN(데이터!E2:E{last})", "#,##0"),
        ("최고 매출 월", f"=INDEX(데이터!A2:A{last},MATCH(MAX(데이터!E2:E{last}),데이터!E2:E{last},0))", "@"),
    ]
    for i, (label, formula, fmt) in enumerate(rows, start=2):
        a, b = sm.cell(row=i, column=1, value=label), sm.cell(row=i, column=2, value=formula)
        a.font = b.font = body_font
        a.border = b.border = border
        b.number_format = fmt
        b.alignment = Alignment(horizontal="right")
    sm.column_dimensions["A"].width = 18
    sm.column_dimensions["B"].width = 16

    chart = BarChart()
    chart.type, chart.style = "col", 10
    chart.title = "월별 매출 합계"
    chart.y_axis.title, chart.x_axis.title = "매출(원)", "월"
    chart.add_data(Reference(ws, min_col=5, min_row=1, max_row=last), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=last))
    chart.series[0].graphicalProperties.solidFill = color
    chart.legend = None
    chart.height, chart.width = 8, 16
    chart.x_axis.delete = False  # openpyxl 3.1 hides axes unless told otherwise
    chart.y_axis.delete = False
    sm.add_chart(chart, "D2")
    return wb


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output", default="output/sample.xlsx")
    ap.add_argument("--color", default=DEFAULT_COLOR)
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    build(parse_color(args.color)).save(out)
    print(f"saved: {out.resolve()}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
