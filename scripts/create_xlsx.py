"""Create a sample Excel workbook with openpyxl.

Sheets:
  데이터  Monthly sales table with an ID column (header style, filter, frozen
          header, number format) plus an auto-generated comparison chart
  요약    Formulas (total / average / max / min / best month) and a bar chart

After the workbook is built, format_workbook() applies the house style:
  - ID column in front of the data (existing unique ID is kept if present)
  - bold titles / headers, italic quotations, 10pt body text
  - percent number formats for rate columns
  - charts picked from the data structure (line / bar / pie)

Usage:
  python scripts/create_xlsx.py [-o output/samples/sample.xlsx] [--color blue]

--color accepts a name (red, blue, green, 빨강, 파랑 ...) or HEX (#1F4E79).
"""
import argparse
import re
import sys
from copy import copy
from datetime import date, datetime
from math import ceil
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string

FONT = "맑은 고딕"
DEFAULT_COLOR = "1F4E79"
BODY_PT = 10
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

# Header vocabulary used to recognise columns (compared in lower case).
ID_HEADERS = {"id", "no", "번호", "순위", "rank", "idx", "index", "seq", "#"}
TITLE_HEADERS = {"제목", "항목명", "구분", "title", "subject"}
QUOTE_HEADERS = {"인용구", "인용문", "quote", "quotation"}
TOTAL_LABELS = {"합계", "총계", "소계", "계", "total", "sum", "subtotal"}
SHARE_WORDS = ("점유율", "비율", "구성비", "share")
RATE_WORDS = ("성장률", "증가율", "증감률", "변화율", "달성률", "점유율", "비율", "비중", "구성비",
              "전년 대비", "전월 대비", "전년대비", "전월대비", "%")
RATE_EN = re.compile(r"\b(rate|share|growth|yoy|mom|qoq|ratio|percent|percentage|pct)\b", re.I)
TIME_HEADERS = {"월", "년", "연도", "년도", "분기", "기간", "날짜", "일자",
                "date", "month", "year", "quarter", "period"}
TIME_VALUE = re.compile(
    r"^((19|20)\d{2}\s*년?(\s*\d{1,2}\s*월)?|\d{1,2}\s*월|[1-4]\s*분기|Q[1-4]|"
    r"(19|20)\d{2}[-./ ]?(Q[1-4]|\d{1,2}))$", re.I)

CHART_W_CM, CHART_H_CM = 14, 8
COL_CM, ROW_CM = 1.7, 0.53  # approximate default cell size, used to avoid overlap


# --------------------------------------------------------------------------- #
# Existing helpers (unchanged behaviour)
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Cell / table helpers
# --------------------------------------------------------------------------- #
def _blank(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _is_formula(v):
    return isinstance(v, str) and v.startswith("=")


def _is_url(s):
    return bool(re.match(r"^(https?://|www\.)", s.strip(), re.I))


def to_number(v):
    """Return a float for numbers and numeric strings (e.g. '1,200'); else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and not _is_formula(v):
        s = v.strip().replace(",", "")
        if s and "%" not in s:
            try:
                return float(s)
            except ValueError:
                return None
    return None


def _norm(h):
    return h.strip().lower() if isinstance(h, str) else ""


def is_total_header(h):
    n = _norm(h)
    return n in TOTAL_LABELS or n.startswith("합계") or n.startswith("total")


def is_rate_header(h):
    n = _norm(h)
    return any(w in n for w in RATE_WORDS) or bool(RATE_EN.search(n))


def is_id_header(h):
    """ID-like headers: ID, No., #, 번호, 순위, Rank ... (punctuation is ignored)."""
    n = _norm(h)
    return n in ID_HEADERS or re.sub(r"[\s.:()]+", "", n) in ID_HEADERS


def _is_running_index(values):
    """True for 1, 2, 3 ... (or 0, 1, 2 ...): a row counter, not a measurement."""
    if len(values) < 3 or values[0] not in (0, 1) or not all(float(v).is_integer() for v in values):
        return False
    return all(b - a == 1 for a, b in zip(values, values[1:]))


def _has_hangul(text):
    return bool(re.search(r"[가-힣]", text))


def is_share_header(h):
    n = _norm(h)
    return any(w in n for w in SHARE_WORDS)


def iter_cells(ws):
    """Yield real cells; merged non-anchor cells are read-only and skipped."""
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell, MergedCell):
                yield cell


def is_empty_sheet(ws):
    return all(_blank(c.value) for c in iter_cells(ws))


def find_header_row(ws):
    """First row with at least two text cells and nothing else.

    A single-cell row above it (e.g. a merged report title) is not a header.
    """
    for r in range(1, ws.max_row + 1):
        vals = [c.value for c in ws[r] if not isinstance(c, MergedCell) and not _blank(c.value)]
        if len(vals) >= 2 and all(isinstance(v, str) and not _is_formula(v) for v in vals):
            return r
    return None


def _table_block(ws, min_rows=2):
    """(header_row, data_rows) for the first table, trimmed before any total row."""
    hr = find_header_row(ws)
    if hr is None:
        return None, []
    rows = []
    for r in range(hr + 1, ws.max_row + 1):
        vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
        if all(_blank(v) for v in vals):
            break  # blank row ends the table
        first_text = next((v for v in vals if isinstance(v, str) and not _is_formula(v) and v.strip()), None)
        if first_text is not None and is_total_header(first_text):
            break  # total / subtotal rows stay out of the chart range
        rows.append(r)
    return (hr, rows) if len(rows) >= min_rows else (hr, [])


def _restyle(cell, **changes):
    """Copy the existing Font and change only the given attributes."""
    font = copy(cell.font)
    if not font.name:
        font.name = FONT
    for key, value in changes.items():
        setattr(font, key, value)
    cell.font = font


# --------------------------------------------------------------------------- #
# 1. ID column
# --------------------------------------------------------------------------- #
def add_id_column(rows):
    """Put an ID column in front of the data rows.

    - An existing first column named ID is kept as is (unique IDs win).
    - Otherwise data rows are numbered 1, 2, 3 ... (header excluded).
    - Blank rows get no ID and do not consume a number.

    This works on the rows before they are written, so formulas, filters and
    chart references can be computed from the final column positions. A plain
    insert_cols() would leave them pointing at the old columns.
    """
    if not rows:
        return rows
    header, body = rows[0], rows[1:]
    if _norm(header[0]) in {"id"}:
        return rows
    out = [("ID",) + tuple(header)]
    n = 0
    for row in body:
        if all(_blank(v) for v in row):
            out.append((None,) + tuple(row))
        else:
            n += 1
            out.append((n,) + tuple(row))
    return out


# --------------------------------------------------------------------------- #
# 2-4. Cell roles and styles
# --------------------------------------------------------------------------- #
def is_quote(value):
    """True for text wrapped in quotation marks or starting with '>'."""
    if not isinstance(value, str) or _is_formula(value):
        return False
    s = value.strip()
    if len(s) < 1 or _is_url(s):
        return False
    if s.startswith(">"):
        return True
    return len(s) >= 2 and s[0] in "\"'“‘" and s[-1] in "\"'”’"


def classify_cells(ws):
    """Map cell coordinate -> set of roles: title, header, titlecol, quote."""
    roles = {}

    def add(cell, role):
        roles.setdefault(cell.coordinate, set()).add(role)

    hr = find_header_row(ws)
    if hr is None:  # fall back to the first non-empty row
        hr = next((r for r in range(1, ws.max_row + 1)
                   if any(isinstance(c.value, str) and not _blank(c.value) for c in ws[r]
                          if not isinstance(c, MergedCell))), None)

    for rng in ws.merged_cells.ranges:  # merged title cells
        cell = ws.cell(rng.min_row, rng.min_col)
        if isinstance(cell.value, str) and not _blank(cell.value) and not _is_formula(cell.value):
            add(cell, "title")
    if hr:
        for r in range(1, hr):  # report title rows above the header
            for cell in ws[r]:
                if not isinstance(cell, MergedCell) and not _blank(cell.value):
                    add(cell, "title")
        for cell in ws[hr]:
            if not isinstance(cell, MergedCell) and not _blank(cell.value):
                add(cell, "header")
        for c in range(1, ws.max_column + 1):
            key = _norm(ws.cell(hr, c).value)
            role = "titlecol" if key in TITLE_HEADERS else "quote" if key in QUOTE_HEADERS else None
            if role:
                for r in range(hr + 1, ws.max_row + 1):
                    cell = ws.cell(r, c)
                    if (not isinstance(cell, MergedCell) and isinstance(cell.value, str)
                            and not _blank(cell.value) and not _is_formula(cell.value)
                            and not _is_url(cell.value)):
                        add(cell, role)
    for cell in iter_cells(ws):  # quotation marks work in any column
        if is_quote(cell.value):
            add(cell, "quote")
    return roles


def apply_header_style(ws, roles=None):
    """Bold for titles, headers and title-column cells; size is kept."""
    roles = roles or classify_cells(ws)
    for cell in iter_cells(ws):
        if roles.get(cell.coordinate, set()) & {"title", "header", "titlecol"}:
            _restyle(cell, b=True)


def apply_quote_style(ws, roles=None):
    """Italic for quotations; numbers, formulas, dates and URLs are never italic."""
    roles = roles or classify_cells(ws)
    for cell in iter_cells(ws):
        if "quote" in roles.get(cell.coordinate, set()) and isinstance(cell.value, str):
            _restyle(cell, i=True)


def apply_body_font(ws, roles=None):
    """10pt for body cells; titles, headers and title columns keep their size.

    Only the size changes, so colour, bold, italic, underline, borders, fill,
    alignment, number format and protection stay as they were.
    """
    roles = roles or classify_cells(ws)
    for cell in iter_cells(ws):
        if _blank(cell.value):
            continue
        if roles.get(cell.coordinate, set()) & {"title", "header", "titlecol"}:
            continue
        _restyle(cell, sz=BODY_PT)


def apply_percent_format(ws):
    """0.15 -> '0.0%'; 15 -> '0.0"%"'. Unclear units keep the original format."""
    hr, rows = _table_block(ws, min_rows=1)
    if hr is None:
        return
    for c in range(1, ws.max_column + 1):
        if not is_rate_header(ws.cell(hr, c).value):
            continue
        cells = [ws.cell(r, c) for r in rows]
        nums = [to_number(x.value) for x in cells if isinstance(x.value, (int, float))
                and not isinstance(x.value, bool)]
        if not nums:
            continue  # formulas / text only: cannot tell the unit
        top = max(abs(n) for n in nums)
        if top <= 1.5:
            fmt = "0.0%"
        elif top <= 1000:  # e.g. an achievement rate of 110 (%) is still a percent number
            fmt = '0.0"%"'
        else:
            continue
        for cell in cells:
            if isinstance(cell.value, (int, float)) and cell.number_format == "General":
                cell.number_format = fmt


# --------------------------------------------------------------------------- #
# 5. Charts
# --------------------------------------------------------------------------- #
def _time_like(header, values):
    """A column is a time axis by its header, by dates, or by text such as '3월'.

    Plain integers only count when the header says so ('연도'); otherwise a
    sales column holding 2021, 2050 ... would be mistaken for years.
    """
    if _norm(header) in TIME_HEADERS:
        return True
    filled = [v for v in values if not _blank(v)]
    if not filled:
        return False
    if all(isinstance(v, (date, datetime)) for v in filled):
        return True
    ok = sum(1 for v in filled if isinstance(v, str) and TIME_VALUE.match(v.strip()))
    return ok / len(filled) >= 0.8


def detect_numeric_columns(ws):
    """Find the category column and the numeric columns that can be charted.

    Returns None when no chart is possible, else a dict with the header row,
    data rows, category column and the value / rate columns as (col, header).
    ID, total and quote columns, blank rows and total rows are left out. Text
    stored numbers such as '1,200' count as numbers if the whole column converts.
    """
    hr, rows = _table_block(ws)
    if hr is None or not rows:
        return None
    cols = []
    for c in range(1, ws.max_column + 1):
        h = ws.cell(hr, c).value
        if not isinstance(h, str) or _blank(h):
            continue
        h = h.strip()
        if is_id_header(h) or _norm(h) in QUOTE_HEADERS or is_total_header(h):
            continue
        cells = [ws.cell(r, c).value for r in rows]
        filled = [v for v in cells if not _blank(v)]
        if not filled:
            continue
        nums = [v for v in filled if to_number(v) is not None]
        formulas = [v for v in filled if _is_formula(v)]
        running = len(nums) == len(filled) and _is_running_index([to_number(v) for v in nums])
        cols.append({
            "col": c, "header": h, "rate": is_rate_header(h), "time": _time_like(h, cells), "index": running,
            "nums": len(nums), "formulas": len(formulas),
            "texts": len(filled) - len(nums) - len(formulas), "n": len(filled),
        })

    # The category is a time column if there is one, else the first text column.
    category = next((x for x in cols if x["time"] and not x["rate"]), None) \
        or next((x for x in cols if x["texts"] == x["n"] and not x["rate"]), None)
    if category is None:
        return None

    values, rates = [], []
    for x in cols:
        if x is category or x["time"] or x["index"]:
            continue
        # Formula cells have no stored result, so only rate columns (usually
        # formulas such as =C3/C2-1) may rely on them.
        numeric = x["texts"] == 0 and (x["nums"] >= 2 or (x["rate"] and x["nums"] + x["formulas"] >= 2))
        if numeric and (x["rate"] or not x["formulas"]):
            (rates if x["rate"] else values).append((x["col"], x["header"]))
    if not (values or rates):
        return None
    return {"header_row": hr, "rows": rows,
            "category": (category["col"], category["header"], category["time"]),
            "values": values, "rates": rates}


def _coerce_text_numbers(ws, cols, rows):
    """Turn '1,200'-style text into numbers so Excel plots them."""
    for c, _h in cols:
        for r in rows:
            cell = ws.cell(r, c)
            if isinstance(cell.value, str) and not _is_formula(cell.value) and to_number(cell.value) is not None:
                n = to_number(cell.value)
                cell.value = int(n) if n.is_integer() else n


def _anchor_cell(chart):
    a = chart.anchor
    if isinstance(a, str):
        col, row = coordinate_from_string(a)
        return column_index_from_string(col), row
    return a._from.col + 1, a._from.row + 1


def _rect(chart, col, row):
    return (col, row, col + ceil(chart.width / COL_CM) - 1, row + ceil(chart.height / ROW_CM) - 1)


def _overlaps(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _free_anchor(ws, chart):
    """Right of the table; moved down until no chart in the sheet overlaps."""
    col, row = ws.max_column + 2, 2
    while True:
        mine = _rect(chart, col, row)
        clash = [o for o in ws._charts
                 if _overlaps(mine, _rect(o, *_anchor_cell(o)))]
        if not clash:
            return f"{get_column_letter(col)}{row}"
        row += mine[3] - mine[1] + 2


def _chart_refs(wb):
    refs = set()
    for sheet in wb.worksheets:
        for ch in sheet._charts:
            for s in ch.series:
                if s.val is not None and s.val.numRef is not None:
                    refs.add(s.val.numRef.f)
    return refs


def no_overlay(chart, legend_bottom=True):
    """Stop the chart title, axis titles and legend from drawing over the plot.

    openpyxl omits <c:overlay>, and Excel then draws these on top of the
    axis labels and data lines.
    """
    titles = [chart.title]
    for axis in ("x_axis", "y_axis"):
        titles.append(getattr(getattr(chart, axis, None), "title", None))
    for t in titles:
        if t is not None and hasattr(t, "overlay"):
            t.overlay = False
    if chart.legend is not None:
        chart.legend.overlay = False
        if legend_bottom:
            chart.legend.position = "b"


def _make_chart(ws, info, cols, kind, title, y_title):
    hr, rows = info["header_row"], info["rows"]
    cat_col, cat_header, _t = info["category"]
    first, last = rows[0], rows[-1]
    if kind == "pie":
        chart = PieChart()
        chart.dataLabels = DataLabelList()
        chart.dataLabels.showPercent = True
    else:
        chart = LineChart() if kind == "line" else BarChart()
        if kind == "bar":
            chart.type = "col"
        chart.x_axis.title, chart.y_axis.title = cat_header, y_title
        chart.x_axis.delete = False  # openpyxl 3.1 hides axes unless told otherwise
        chart.y_axis.delete = False
    for c, _h in cols:
        chart.add_data(Reference(ws, min_col=c, min_row=hr, max_row=last), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=cat_col, min_row=first, max_row=last))
    if kind == "line":
        for s in chart.series:
            s.marker.symbol, s.smooth = "circle", False
    chart.title = title
    chart.width, chart.height = CHART_W_CM, CHART_H_CM
    no_overlay(chart)
    return chart


def create_chart_if_needed(ws):
    """Create the charts the data structure calls for; returns a log of them.

    Time categories -> line chart, other categories -> bar chart, a share
    column with at most 7 items that sums to 1 or 100 -> pie chart. Value and
    rate columns get separate charts because their scales differ.
    """
    log = []
    if ws._charts:
        log.append(f"[{ws.title}] 이미 차트가 있어 새 차트를 만들지 않았습니다.")
        return log
    info = detect_numeric_columns(ws)
    if info is None:
        log.append(f"[{ws.title}] 차트 조건(범주 열 + 숫자 열)이 맞지 않아 차트를 만들지 않았습니다.")
        return log

    _cat_col, cat_header, time_like = info["category"]
    kind = "line" if time_like else "bar"
    verb = "추이" if time_like else "비교"
    values, rates = list(info["values"]), list(info["rates"])
    plans = []  # (cols, kind, title, y_title)

    ko = _has_hangul(cat_header + "".join(h for _c, h in values + rates))  # title language

    def title_for(cols, more=False):
        if ko:
            return f"{cat_header}별 {'·'.join(h for _c, h in cols[:3])}{' 등' if more else ''} {verb}"
        return f"{', '.join(h for _c, h in cols[:3])}{' etc.' if more else ''} by {cat_header}"

    for col in [x for x in rates if is_share_header(x[1])]:
        nums = [to_number(ws.cell(r, col[0]).value) for r in info["rows"]]
        total = sum(n for n in nums if n is not None)
        if len(info["rows"]) <= 7 and (0.98 <= total <= 1.02 or 98 <= total <= 102):
            plans.append(([col], "pie", f"{col[1]} 구성비" if ko else f"{col[1]} breakdown", ""))
            rates.remove(col)
            break
    # Rates stored as fractions (0.19) and as percent numbers (3.5) differ by a factor
    # of 100, so each group gets its own chart.
    fractions, percents = [], []
    for col in rates:
        mags = [abs(n) for n in (to_number(ws.cell(r, col[0]).value) for r in info["rows"]) if n is not None]
        (percents if mags and max(mags) > 1.5 else fractions).append(col)
    for group in (fractions, percents):
        if group:
            plans.append((group, kind, title_for(group), "비율" if ko else "Rate"))
    if values:
        plans.append((values, kind, title_for(values, len(values) > 3),
                      values[0][1] if len(values) == 1 else ("수치" if ko else "Value")))

    existing = _chart_refs(ws.parent)
    for cols, k, title, y_title in plans:
        _coerce_text_numbers(ws, cols, info["rows"])
        chart = _make_chart(ws, info, cols, k, title, y_title)
        refs = {s.val.numRef.f for s in chart.series}
        if refs <= existing:
            log.append(f"[{ws.title}] '{title}'는 같은 데이터의 차트가 있어 건너뜁니다.")
            continue
        anchor = _free_anchor(ws, chart)
        ws.add_chart(chart, anchor)
        existing |= refs
        log.append(f"[{ws.title}] {k} 차트 '{title}' → {anchor} (범위: {', '.join(sorted(refs))})")
    return log


# --------------------------------------------------------------------------- #
# 6. Whole workbook
# --------------------------------------------------------------------------- #
def format_workbook(workbook):
    """Apply fonts, number formats and charts to every sheet of the workbook."""
    if not workbook.worksheets:
        print("워크북에 시트가 없어 서식을 적용하지 않았습니다.")
        return
    for ws in workbook.worksheets:
        if is_empty_sheet(ws):
            print(f"[{ws.title}] 시트가 비어 있어 건너뜁니다.")
            continue
        if ws.protection.sheet:
            print(f"[{ws.title}] 보호된 시트입니다. 서식은 적용하지만 Excel에서 보호가 유지됩니다.")
        try:
            roles = classify_cells(ws)
            apply_header_style(ws, roles)
            apply_quote_style(ws, roles)
            apply_body_font(ws, roles)
            apply_percent_format(ws)
            for line in create_chart_if_needed(ws):
                print(line)
        except Exception as exc:  # noqa: BLE001 - keep going with the other sheets
            print(f"[{ws.title}] 서식 적용 중 오류가 발생해 이 시트는 건너뜁니다: {exc}")


# --------------------------------------------------------------------------- #
# Workbook build (existing logic, now offset by the ID column)
# --------------------------------------------------------------------------- #
def build(color):
    wb = Workbook()
    thin = Side(style="thin", color=color)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor=color)
    head_font = Font(name=FONT, bold=True, color=text_on(color))
    body_font = Font(name=FONT)

    rows = add_id_column(DATA)
    ncols = len(rows[0])
    offset = ncols - len(DATA[0])  # 1 when an ID column was added
    cat_col = 1 + offset           # 월
    val_first, val_last = 2 + offset, ncols
    total_col = ncols + 1          # 합계 formula column
    last = len(rows)
    L = get_column_letter
    first_v, last_v, tot, cat = L(val_first), L(val_last), L(total_col), L(cat_col)

    # ---- 데이터 sheet ----
    ws = wb.active
    ws.title = "데이터"
    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.border = border
            if r == 1:
                cell.font, cell.fill = head_font, head_fill
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.font = body_font
                if offset and c == 1:
                    cell.alignment = Alignment(horizontal="center")
                elif c >= val_first:
                    cell.number_format = "#,##0"
    ws.freeze_panes = "A2"
    for c in range(1, ncols + 1):
        ws.column_dimensions[L(c)].width = 8 if (offset and c == 1) else 14
    ws.row_dimensions[1].height = 24

    # Row total per month goes in the 합계 column so the best month can be looked up.
    ws.cell(1, total_col, "합계")
    ws.cell(1, total_col).font, ws.cell(1, total_col).fill = head_font, head_fill
    ws.cell(1, total_col).alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(1, total_col).border = border
    ws.column_dimensions[tot].width = 14
    for r in range(2, last + 1):
        cell = ws.cell(r, total_col, f"=SUM({first_v}{r}:{last_v}{r})")
        cell.number_format = "#,##0"
        cell.font = body_font
        cell.border = border
    ws.auto_filter.ref = f"A1:{tot}{last}"

    # ---- 요약 sheet ----
    sm = wb.create_sheet("요약")
    sm["A1"], sm["B1"] = "항목", "값"
    for cell in (sm["A1"], sm["B1"]):
        cell.font, cell.fill = head_font, head_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = border

    tot_rng = f"데이터!{tot}2:{tot}{last}"
    summary = [
        ("전체 매출 합계", f"=SUM({tot_rng})", "#,##0"),
        ("월 평균 매출", f"=AVERAGE({tot_rng})", "#,##0"),
        ("최고 월 매출", f"=MAX({tot_rng})", "#,##0"),
        ("최저 월 매출", f"=MIN({tot_rng})", "#,##0"),
        ("최고 매출 월", f"=INDEX(데이터!{cat}2:{cat}{last},MATCH(MAX({tot_rng}),{tot_rng},0))", "@"),
    ]
    for i, (label, formula, fmt) in enumerate(summary, start=2):
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
    chart.add_data(Reference(ws, min_col=total_col, min_row=1, max_row=last), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=cat_col, min_row=2, max_row=last))
    chart.series[0].graphicalProperties.solidFill = color
    chart.legend = None
    chart.height, chart.width = 8, 16
    chart.x_axis.delete = False  # openpyxl 3.1 hides axes unless told otherwise
    chart.y_axis.delete = False
    no_overlay(chart)
    sm.add_chart(chart, "D2")

    format_workbook(wb)
    return wb


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output", default="output/samples/sample.xlsx")
    ap.add_argument("--color", default=DEFAULT_COLOR)
    args = ap.parse_args()

    out = Path(args.output)
    if out.suffix.lower() not in (".xlsx", ".xlsm"):
        print(f"출력 파일 확장자는 .xlsx 여야 합니다: {out}")
        return 1
    if out.resolve() == Path(__file__).resolve():
        print(f"출력 경로가 이 스크립트 파일과 같아 덮어쓸 수 없습니다: {out}")
        return 1
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"출력 폴더를 만들 수 없습니다: {out.parent}\n{exc}")
        return 1

    wb = build(parse_color(args.color))
    try:
        wb.save(out)
    except PermissionError:
        print(f"저장할 수 없습니다: {out}\n엑셀 파일이 열려 있는지 확인하세요.")
        return 1
    except OSError as exc:
        print(f"저장 중 오류가 발생했습니다: {out}\n{exc}")
        return 1
    print(f"saved: {out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
