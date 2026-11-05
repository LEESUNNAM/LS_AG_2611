"""Command-line helpers for building and analysing Excel files with openpyxl.

Built on the bundled create_xlsx.py (same folder), whose format_workbook()
gives every workbook the house style: ID column, bold headers, italic quotes,
10pt 맑은 고딕 body, percent formats and charts picked from the data.

Commands:
  create   Build a new .xlsx from a JSON spec (sheets, headers, rows, formulas).
  inspect  Describe a .xlsx / .csv / .tsv: sheets, header row, column types,
           statistics, formulas, merged cells, data-quality issues.
           --export-spec writes the tables as a spec you can extend and pass
           to `create`.
  format   Apply the house style (no ID column) to a copy of an existing file.

Run it as `python <dir>/xlsx_tools.py ...` (not with -I) so create_xlsx.py is found.

Examples:
  python xlsx_tools.py create spec.json -o output/report.xlsx --color blue
  python xlsx_tools.py inspect data.xlsx
  python xlsx_tools.py inspect data.csv --json
  python xlsx_tools.py inspect data.xlsx --export-spec spec.json
  python xlsx_tools.py format data.xlsx -o output/data_formatted.xlsx

Spec format (cell values: text, numbers, null, true/false, or "=FORMULA"):
  {
    "title": "Workbook title",
    "color": "navy",
    "sheets": [
      {"name": "데이터",
       "title": "Optional report title written above the table (merged)",
       "headers": ["월", "제품A", "제품B"],
       "rows": [["1월", 100, 90], ["2월", 120, 95]],
       "formats": {"제품A": "#,##0"},
       "notes": ["Free text lines written under the table"],
       "id": true}
    ]
  }

Spec coordinates: write formulas as if the sheet had no ID column and no title
row, so the header is row 1 and the first data row is row 2 (column A is the
first header). `create` shifts references automatically when it adds the ID
column (+1 column) or a title row (+1 row), including references to other
sheets. Sheets get an ID column unless "id": false.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formula import Tokenizer
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import column_index_from_string, get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import create_xlsx as cx  # noqa: E402  (bundled sibling module)

BAD_SHEET_CHARS = set('[]:*?/\\')
CSV_ENCODINGS = ("utf-8-sig", "cp949", "utf-8")
LONG_TEXT = 50  # longer text wraps


# --------------------------------------------------------------------------- #
# Formula reference shifting
# --------------------------------------------------------------------------- #
_CELL = re.compile(r"^(\$?)([A-Za-z]{1,3})(\$?)(\d*)$")


def _shift_part(part, dcol, drow, warn):
    m = _CELL.match(part)
    if not m:
        return part, False
    c_abs, col, r_abs, row = m.groups()
    out = f"{c_abs}{get_column_letter(column_index_from_string(col.upper()) + dcol)}{r_abs}"
    if row:
        new_row = int(row) + drow
        if new_row < 1:
            warn(f"reference to row {row} moved above row 1 and was clamped")
            new_row = 1
        out += str(new_row)
    return out, True


def _shift_operand(v, own, dcol_map, drow_map, warn):
    if "!" in v:
        sheet_part, ref = v.rsplit("!", 1)
        sheet = sheet_part[1:-1].replace("''", "'") if sheet_part.startswith("'") else sheet_part
        prefix = sheet_part + "!"
    else:
        sheet, ref, prefix = own, v, ""
    dcol, drow = dcol_map.get(sheet, 0), drow_map.get(sheet, 0)
    if not (dcol or drow):
        return v
    parts = ref.split(":")
    if len(parts) == 1:
        if not re.search(r"\d", parts[0]):
            return v  # a defined name, not a cell
        new, ok = _shift_part(parts[0], dcol, drow, warn)
        return prefix + new if ok else v
    if len(parts) == 2:
        shifted = []
        for p in parts:
            new, ok = _shift_part(p, dcol, drow, warn)
            if not ok:
                return v
            shifted.append(new)
        return prefix + ":".join(shifted)
    return v


def shift_formula(formula, own_sheet, dcol_map, drow_map, warn=lambda _m: None):
    """Move cell references: dcol_map / drow_map give the shift per target sheet."""
    if not (isinstance(formula, str) and formula.startswith("=")):
        return formula
    try:
        tok = Tokenizer(formula)
    except Exception:  # noqa: BLE001 - leave unparseable formulas alone
        return formula
    parts = []
    for t in tok.items:
        v = t.value
        if t.type == "OPERAND" and t.subtype == "RANGE":
            v = _shift_operand(v, own_sheet, dcol_map, drow_map, warn)
        parts.append(v)
    return "=" + "".join(parts)


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_any(path, data_only=False):
    """Return (workbook, notes) for .xlsx/.xlsm/.csv/.tsv."""
    p = Path(path)
    if not p.is_file():
        sys.exit(f"file not found: {p}")
    ext = p.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        try:
            return load_workbook(p, data_only=data_only), []
        except Exception as exc:  # noqa: BLE001
            sys.exit(f"cannot open {p.name}: {exc}")
    if ext == ".xls":
        sys.exit(f"{p.name}: .xls is not supported by openpyxl. Save it as .xlsx in Excel and retry.")
    if ext in (".csv", ".tsv"):
        raw, used = None, None
        for enc in CSV_ENCODINGS:
            try:
                raw, used = p.read_text(encoding=enc), enc
                break
            except UnicodeDecodeError:
                continue
        if raw is None:
            sys.exit(f"cannot decode {p.name} as UTF-8 or CP949")
        delimiter = "\t" if ext == ".tsv" else None
        if delimiter is None:
            try:
                delimiter = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t|").delimiter
            except csv.Error:
                delimiter = ","
        rows = list(csv.reader(raw.splitlines(), delimiter=delimiter))
        wb = Workbook()
        ws = wb.active
        ws.title = p.stem[:31] or "Sheet1"
        for r in rows:
            ws.append(r)
        notes = [f"csv decoded as {used}, delimiter {delimiter!r}"]
        for c in range(1, ws.max_column + 1):  # whole-column text numbers -> numbers
            cells = [ws.cell(r, c) for r in range(2, ws.max_row + 1) if not cx._blank(ws.cell(r, c).value)]
            if cells and all(cx.to_number(x.value) is not None for x in cells):
                for x in cells:
                    n = cx.to_number(x.value)
                    x.value = int(n) if n.is_integer() else n
                notes.append(f"column {get_column_letter(c)} converted from text to numbers")
        return wb, notes
    sys.exit(f"unsupported file type {ext!r}. Supported: .xlsx .xlsm .csv .tsv")


def _json_safe(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    return v


# --------------------------------------------------------------------------- #
# inspect
# --------------------------------------------------------------------------- #
def _round(x):
    return round(x, 6) if isinstance(x, float) else x


def _classify_rows(ws, hr):
    """Row numbers after the header: data / blank / total rows, plus note rows.

    Note rows are lines with a single text cell at the very end of the sheet,
    separated from the table by a blank row (the layout `create` writes for
    "notes"). They are not part of the table.
    """
    last = 0
    for r in range(ws.max_row, hr, -1):
        if any(not cx._blank(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)):
            last = r
            break
    data, blank, total = [], [], []
    for r in range(hr + 1, last + 1):
        vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
        if all(cx._blank(v) for v in vals):
            blank.append(r)
            continue
        first_text = next((v for v in vals if isinstance(v, str) and not cx._is_formula(v) and v.strip()), None)
        if first_text is not None and cx.is_total_header(first_text):
            total.append(r)
        else:
            data.append(r)

    def single_text(r):
        vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1) if not cx._blank(ws.cell(r, c).value)]
        return len(vals) == 1 and isinstance(vals[0], str) and not cx._is_formula(vals[0])

    tail, r = [], last
    while r > hr and r in data and single_text(r):
        tail.append(r)
        r -= 1
    notes = []
    if tail and r in blank:  # the block is only "notes" if a blank row separates it from the table
        notes = sorted(tail)
        data = [x for x in data if x not in tail]
        while r in blank:
            blank.remove(r)
            r -= 1
        last = r
    return data, blank, total, last, notes


def _analyze_column(ws, wsv, c, header, data_rows):
    nums, text_nums, texts, dates = [], [], [], 0
    formulas = nocache = empty = 0
    for r in data_rows:
        fv, vv = ws.cell(r, c).value, wsv.cell(r, c).value
        if cx._blank(fv):
            empty += 1
            continue
        if cx._is_formula(fv):
            formulas += 1
            val = vv
            if val is None:
                nocache += 1
                continue
        else:
            val = fv
        if isinstance(val, bool):
            texts.append(str(val))
        elif isinstance(val, (int, float)):
            nums.append(float(val))
        elif isinstance(val, (date, datetime)):
            dates += 1
        else:
            n = cx.to_number(val) if isinstance(val, str) else None
            (text_nums if n is not None else texts).append(n if n is not None else str(val))
    col = {"column": get_column_letter(c), "header": header, "empty": empty, "formulas": formulas}
    kinds = {"number": len(nums), "text-number": len(text_nums), "text": len(texts), "date": dates}
    col["type"] = max(kinds, key=kinds.get) if any(kinds.values()) else "empty"
    col["counts"] = {k: v for k, v in kinds.items() if v}
    if nocache:
        col["formulas_without_cached_value"] = nocache
    if nums:
        col["stats"] = {"n": len(nums), "min": _round(min(nums)), "max": _round(max(nums)),
                        "sum": _round(sum(nums)), "mean": _round(sum(nums) / len(nums))}
    if text_nums:
        allv = nums + [float(x) for x in text_nums]
        col["stats_if_text_numbers_converted"] = {
            "n": len(allv), "min": _round(min(allv)), "max": _round(max(allv)),
            "sum": _round(sum(allv)), "mean": _round(sum(allv) / len(allv))}
    if texts:
        counts = Counter(texts)
        col["distinct_text"] = len(counts)
        col["top_text"] = [[t[:40], n] for t, n in counts.most_common(5)]
    if cx.is_rate_header(header) and (nums or text_nums):
        top = max(abs(x) for x in nums + [float(y) for y in text_nums])
        col["rate_unit_guess"] = "fraction (0.15 = 15%)" if top <= 1.5 else "percent number (15 = 15%)"
    return col


def analyze(path, sample_rows=5):
    wf, notes = load_any(path, data_only=False)
    suffix = Path(path).suffix.lower()
    wv = load_any(path, data_only=True)[0] if suffix in (".xlsx", ".xlsm") else wf
    report = {"file": str(path), "notes": notes, "sheets": []}
    for ws in wf.worksheets:
        wsv = wv[ws.title]
        if cx.is_empty_sheet(ws):
            report["sheets"].append({"name": ws.title, "empty": True})
            continue
        issues = []
        hr = cx.find_header_row(ws)
        info = {"name": ws.title, "dimensions": ws.dimensions, "merged": [str(r) for r in ws.merged_cells.ranges],
                "charts": len(ws._charts), "images": len(getattr(ws, "_images", [])),
                "protected": bool(ws.protection.sheet)}
        if hr is None:
            issues.append("no header row found (needs a row with at least two text cells)")
            info["issues"] = issues
            info["first_rows"] = [[_json_safe(ws.cell(r, c).value) for c in range(1, min(ws.max_column, 12) + 1)]
                                  for r in range(1, min(ws.max_row, sample_rows) + 1)]
            report["sheets"].append(info)
            continue
        titles = [str(ws.cell(r, c).value).strip() for r in range(1, hr)
                  for c in range(1, ws.max_column + 1) if not cx._blank(ws.cell(r, c).value)]
        data_rows, blank_rows, total_rows, last, note_rows = _classify_rows(ws, hr)
        info["notes"] = [next(str(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)
                              if not cx._blank(ws.cell(r, c).value)) for r in note_rows]
        info.update({"title_text": titles, "header_row": hr, "data_rows": len(data_rows),
                     "first_data_row": data_rows[0] if data_rows else None,
                     "last_data_row": data_rows[-1] if data_rows else None,
                     "blank_rows_in_table": blank_rows, "total_rows": total_rows})
        columns = []
        for c in range(1, ws.max_column + 1):
            h = ws.cell(hr, c).value
            header = str(h).strip() if not cx._blank(h) else f"(col {get_column_letter(c)})"
            columns.append(_analyze_column(ws, wsv, c, header, data_rows))
        info["columns"] = columns
        names = [x["header"] for x in columns]
        if len(set(names)) != len(names):
            issues.append("duplicate header names: " + ", ".join(k for k, v in Counter(names).items() if v > 1))
        for col in columns:
            if col["counts"].get("text-number"):
                issues.append(f"column {col['column']} '{col['header']}': {col['counts']['text-number']} number(s) stored as text")
            if col.get("formulas_without_cached_value"):
                issues.append(f"column {col['column']} '{col['header']}': formulas have no stored result "
                              "(file was not saved by Excel), so their values are unknown here")
            if len(col["counts"]) > 1 and col["type"] in ("number", "text") and \
                    {"number", "text"} <= set(col["counts"]):
                issues.append(f"column {col['column']} '{col['header']}': mixes numbers and text")
        if blank_rows:
            issues.append(f"blank row(s) inside the table: {blank_rows}")
        if total_rows:
            issues.append(f"total/subtotal row(s) at {total_rows}: leave them out of sums and charts")
        in_table = [m for m in ws.merged_cells.ranges if m.min_row >= hr]  # a merged title above the header is fine
        if in_table:
            issues.append("merged cells inside the table: " + ", ".join(str(m) for m in in_table[:6]))
        dup = len(data_rows) - len({tuple(ws.cell(r, c).value for c in range(1, ws.max_column + 1)) for r in data_rows})
        if dup:
            issues.append(f"{dup} duplicate data row(s)")
        if ws.protection.sheet:
            issues.append("sheet is protected")
        if info["charts"]:
            issues.append(f"{info['charts']} chart(s) exist; openpyxl may not keep every chart detail")
        info["issues"] = issues
        info["sample_rows"] = [[_json_safe(wsv.cell(r, c).value if wsv.cell(r, c).value is not None
                                           else ws.cell(r, c).value) for c in range(1, ws.max_column + 1)]
                               for r in data_rows[:sample_rows]]
        info["_header_row_values"] = [ws.cell(hr, c).value for c in range(1, ws.max_column + 1)]
        report["sheets"].append(info)
    return report


def print_report(rep):
    print(f"file: {rep['file']}")
    for n in rep["notes"]:
        print(f"note: {n}")
    for s in rep["sheets"]:
        print(f"\n== sheet '{s['name']}' ==")
        if s.get("empty"):
            print("  (empty)")
            continue
        print(f"  dimensions {s['dimensions']}  charts={s['charts']} images={s['images']} protected={s['protected']}")
        if "header_row" not in s:
            print("  header row not found. First rows:")
            for row in s["first_rows"]:
                print("   ", row)
        else:
            if s["title_text"]:
                print(f"  title text above table: {' / '.join(s['title_text'])}")
            print(f"  header row {s['header_row']}; {s['data_rows']} data rows "
                  f"(rows {s['first_data_row']}-{s['last_data_row']})")
            for col in s["columns"]:
                line = f"  {col['column']} '{col['header']}' [{col['type']}]"
                if "stats" in col:
                    st = col["stats"]
                    line += f" n={st['n']} min={st['min']} max={st['max']} sum={st['sum']} mean={st['mean']}"
                if "stats_if_text_numbers_converted" in col:
                    st = col["stats_if_text_numbers_converted"]
                    line += f" | if text numbers converted: sum={st['sum']} mean={st['mean']}"
                if "distinct_text" in col:
                    top = ", ".join(f"{t}({n})" for t, n in col["top_text"][:3])
                    line += f" distinct={col['distinct_text']} top: {top}"
                if col["formulas"]:
                    line += f" formulas={col['formulas']}"
                if col["empty"]:
                    line += f" empty={col['empty']}"
                if "rate_unit_guess" in col:
                    line += f" unit: {col['rate_unit_guess']}"
                print(line)
            print("  sample rows:")
            for row in s["sample_rows"]:
                print("   ", row)
            if s.get("notes"):
                print(f"  notes under the table ({len(s['notes'])}):")
                for n in s["notes"]:
                    print(f"    - {n[:100]}")
        if s.get("issues"):
            print("  issues:")
            for i in s["issues"]:
                print(f"   - {i}")


def export_spec(path):
    """Turn the tables of a file into a spec (table coordinates: header = row 1)."""
    wf, _notes = load_any(path, data_only=False)
    sheets, row_by = [], {}
    for ws in wf.worksheets:
        if cx.is_empty_sheet(ws):
            continue
        hr = cx.find_header_row(ws)
        if hr is None:
            print(f"skipped sheet '{ws.title}': no header row found", file=sys.stderr)
            continue
        row_by[ws.title] = 1 - hr
    for ws in wf.worksheets:
        if ws.title not in row_by:
            continue
        hr = 1 - row_by[ws.title]
        _data, _blank, _total, last, note_rows = _classify_rows(ws, hr)
        ncols = max((c for c in range(1, ws.max_column + 1)
                     if any(not cx._blank(ws.cell(r, c).value) for r in range(hr, last + 1))), default=0)
        titles = [str(ws.cell(r, c).value).strip() for r in range(1, hr)
                  for c in range(1, ncols + 1) if not cx._blank(ws.cell(r, c).value)]
        warns = []
        rows = [[_json_safe(shift_formula(ws.cell(r, c).value, ws.title, {}, row_by, warns.append))
                 for c in range(1, ncols + 1)] for r in range(hr + 1, last + 1)]
        headers = [("" if cx._blank(ws.cell(hr, c).value) else str(ws.cell(hr, c).value)) for c in range(1, ncols + 1)]
        formats = {}
        if last > hr:
            for c, h in enumerate(headers, 1):
                fmt = ws.cell(hr + 1, c).number_format
                if h and fmt != "General":
                    formats[h] = fmt
        sheet = {"name": ws.title, "headers": headers, "rows": rows}
        if titles:
            sheet["title"] = " / ".join(titles)
        if note_rows:
            sheet["notes"] = [next(str(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)
                                   if not cx._blank(ws.cell(r, c).value)) for r in note_rows]
        if formats:
            sheet["formats"] = formats
        if warns:
            print(f"warning in '{ws.title}': {sorted(set(warns))}", file=sys.stderr)
        sheets.append(sheet)
    return {"title": Path(path).stem, "sheets": sheets}


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
def _display_len(v):
    s = "" if v is None else str(v)
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def _validate_spec(spec):
    sheets = spec.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        sys.exit("spec needs a non-empty 'sheets' list")
    seen = set()
    for sh in sheets:
        name = sh.get("name")
        if not isinstance(name, str) or not name or len(name) > 31 or BAD_SHEET_CHARS & set(name):
            sys.exit(f"bad sheet name {name!r}: 1-31 characters, none of {''.join(sorted(BAD_SHEET_CHARS))}")
        if name in seen:
            sys.exit(f"duplicate sheet name {name!r}")
        seen.add(name)
        hdr = sh.get("headers")
        if not isinstance(hdr, list) or not hdr:
            sys.exit(f"sheet {name!r} needs a non-empty 'headers' list")
        for i, row in enumerate(sh.get("rows", []), 1):
            if len(row) > len(hdr):
                sys.exit(f"sheet {name!r} row {i} has {len(row)} cells but there are {len(hdr)} headers")


def _is_total_row(row):
    first_text = next((v for v in row if isinstance(v, str) and not cx._is_formula(v) and v.strip()), None)
    return first_text is not None and cx.is_total_header(first_text)


def build_workbook(spec, color):
    _validate_spec(spec)
    sheets = spec["sheets"]
    adds_id = {sh["name"]: bool(sh.get("id", True)) and str(sh["headers"][0]).strip().lower() != "id"
               for sh in sheets}
    dcol = {n: 1 for n, v in adds_id.items() if v}
    drow = {sh["name"]: 1 for sh in sheets if sh.get("title")}
    warnings = []

    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.title = str(spec.get("title", ""))
    thin = Side(style="thin", color=color)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor=color)
    head_font = Font(name=cx.FONT, bold=True, color=cx.text_on(color))
    body_font = Font(name=cx.FONT)

    for sh in sheets:
        name = sh["name"]
        ws = wb.create_sheet(name)
        headers = [str(h) for h in sh["headers"]]
        rows = [list(r) + [None] * (len(headers) - len(r)) for r in sh.get("rows", [])]
        formats = sh.get("formats", {})
        if adds_id[name]:
            n, with_id = 0, []
            for r in rows:
                if all(cx._blank(v) for v in r) or _is_total_row(r):
                    with_id.append([None] + r)
                else:
                    n += 1
                    with_id.append([n] + r)
            headers, rows = ["ID"] + headers, with_id
            formats = {**formats}
        rows = [[shift_formula(v, name, dcol, drow, warnings.append) for v in r] for r in rows]

        top = 1
        if sh.get("title"):
            ws.cell(1, 1, str(sh["title"]))
            if len(headers) > 1:
                ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
            ws.cell(1, 1).font = Font(name=cx.FONT, size=14, bold=True)
            ws.cell(1, 1).alignment = Alignment(vertical="center")
            ws.row_dimensions[1].height = 28
            top = 2
        for c, h in enumerate(headers, 1):
            cell = ws.cell(top, c, h)
            cell.font, cell.fill, cell.border = head_font, head_fill, border
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[top].height = 24
        widths = [max(_display_len(h) + 2, 8) for h in headers]
        col_fmt = {}
        for i, r in enumerate(rows, top + 1):
            for c, v in enumerate(r, 1):
                cell = ws.cell(i, c, v)
                cell.font, cell.border = body_font, border
                is_id = adds_id[name] and c == 1
                if is_id:
                    cell.alignment = Alignment(horizontal="center")
                if isinstance(v, str) and not cx._is_formula(v) and len(v) > LONG_TEXT:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
                header = headers[c - 1]
                if header in formats:
                    cell.number_format = formats[header]
                elif isinstance(v, int) and not isinstance(v, bool) and abs(v) >= 1000 and not is_id:
                    cell.number_format = "#,##0"
                    col_fmt.setdefault(c, "#,##0")
                shown = 12 if cx._is_formula(v) else min(_display_len(v), LONG_TEXT)
                widths[c - 1] = max(widths[c - 1], shown + 2)
        # Formula cells have no value to inspect, so they follow the number
        # format of the literal numbers above them in the same column.
        for i, r in enumerate(rows, top + 1):
            for c, v in enumerate(r, 1):
                if c in col_fmt and cx._is_formula(v) and headers[c - 1] not in formats:
                    ws.cell(i, c).number_format = col_fmt[c]
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = min(w, 60)
        if adds_id[name]:
            ws.column_dimensions["A"].width = 7
        last = top + len(rows)
        ws.freeze_panes = ws.cell(top + 1, 1)
        if rows:
            ws.auto_filter.ref = f"A{top}:{get_column_letter(len(headers))}{last}"
        note_col = 2 if adds_id[name] else 1  # first header column, not the ID column
        for k, note in enumerate(sh.get("notes", []), 2):  # one blank row ends the table
            ws.cell(last + k, note_col, str(note)).font = body_font
    for w in sorted(set(warnings)):
        print(f"warning: {w}", file=sys.stderr)
    return wb


def save_workbook(wb, out):
    out = Path(out)
    if out.suffix.lower() != ".xlsx":
        print(f"출력 파일 확장자는 .xlsx 여야 합니다: {out}")
        return 1
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out)
    except PermissionError:
        print(f"저장할 수 없습니다: {out}\n엑셀 파일이 열려 있는지 확인하세요.")
        return 1
    except OSError as exc:
        print(f"저장 중 오류가 발생했습니다: {out}\n{exc}")
        return 1
    print(f"saved: {out.resolve()}")
    return 0


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_create(args):
    if Path(args.output).suffix.lower() != ".xlsx":
        print(f"출력 파일 확장자는 .xlsx 여야 합니다: {args.output}")
        return 1
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        print(f"spec file not found: {spec_path}")
        return 1
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        print(f"spec is not valid JSON: {exc}")
        return 1
    color = cx.parse_color(args.color or spec.get("color") or cx.DEFAULT_COLOR)
    wb = build_workbook(spec, color)
    if not args.no_format:
        cx.format_workbook(wb)
    return save_workbook(wb, args.output)


def cmd_inspect(args):
    rep = analyze(args.file, args.rows)
    if args.export_spec:
        spec = export_spec(args.file)
        Path(args.export_spec).parent.mkdir(parents=True, exist_ok=True)
        Path(args.export_spec).write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"spec written: {args.export_spec}  ({len(spec['sheets'])} sheet(s))", file=sys.stderr)
    for s in rep["sheets"]:
        s.pop("_header_row_values", None)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    else:
        print_report(rep)
    return 0


def cmd_format(args):
    src, out = Path(args.file), Path(args.output)
    if src.resolve() == out.resolve():
        print(f"원본과 출력 경로가 같습니다. 원본은 덮어쓰지 않습니다: {out}")
        return 1
    wb, notes = load_any(src)
    for n in notes:
        print(f"note: {n}")
    print("note: openpyxl can drop pivot tables, macros and slicers when it re-saves a workbook.")
    cx.format_workbook(wb)
    return save_workbook(wb, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create", help="build a .xlsx from a JSON spec")
    p.add_argument("spec")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--color", help="main color: name or HEX (default 1F4E79)")
    p.add_argument("--no-format", action="store_true", help="skip the house style pass")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("inspect", help="describe a .xlsx / .csv / .tsv file")
    p.add_argument("file")
    p.add_argument("--rows", type=int, default=5, help="sample rows per sheet (default 5)")
    p.add_argument("--json", action="store_true", help="print JSON instead of text")
    p.add_argument("--export-spec", metavar="OUT.json", help="also write the tables as a spec")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("format", help="apply the house style to a copy of a file")
    p.add_argument("file")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(func=cmd_format)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
