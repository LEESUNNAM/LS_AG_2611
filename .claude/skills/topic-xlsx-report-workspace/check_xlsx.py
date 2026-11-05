"""Grade one topic-xlsx-report run by inspecting the produced .xlsx.

Usage:
  python check_xlsx.py <run-dir> --mode topic|file --color blue|red|green --lang ko|en
                       [--input-sha <file with the original sha256> --input <original file>]

Reads <run-dir>/outputs/*.xlsx and writes <run-dir>/grading.json in the format the
skill-creator viewer expects (text / passed / evidence). Formula values are read
from a copy recalculated by Excel, which also proves that Excel can open the file.
"""
import argparse
import colorsys
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "topic-xlsx-report" / "scripts"))
import create_xlsx as cx  # noqa: E402

HUE_RANGES = {"blue": [(190, 255)], "red": [(0, 18), (342, 360)], "green": [(80, 170)]}
NOTE_SHEET = re.compile(r"^(요약|summary|출처|sources?|references?|분석( 요약)?|analysis|메모|notes?)$", re.I)
SOURCE_SHEET = re.compile(r"^(출처|sources?|references?)$", re.I)


def in_family(hex_, family):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, s, _v = colorsys.rgb_to_hsv(r, g, b)
    h *= 360
    return s >= 0.25 and any(lo <= h <= hi for lo, hi in HUE_RANGES[family])


def recalc(path, tmpdir):
    out = Path(tmpdir) / "recalc.xlsx"
    r = subprocess.run(["powershell", "-NoProfile", "-File", str(HERE / "recalc.ps1"), str(path), str(out)],
                       capture_output=True, text=True, timeout=120)
    return (out if r.returncode == 0 and out.exists() else None), (r.stdout + r.stderr).strip()


def header_row_of(ws):
    return cx.find_header_row(ws)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--mode", required=True, choices=("topic", "file"))
    ap.add_argument("--color", required=True, choices=HUE_RANGES)
    ap.add_argument("--lang", required=True, choices=("ko", "en"))
    ap.add_argument("--input")
    ap.add_argument("--input-sha")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    exp = []

    def add(text, passed, evidence):
        exp.append({"text": text, "passed": bool(passed), "evidence": str(evidence)})

    files = sorted((run_dir / "outputs").glob("*.xlsx"))
    if not files:
        add("An .xlsx file was produced", False, "no .xlsx in outputs/")
        return finish(run_dir, exp)
    path = files[0]
    try:
        wf = load_workbook(path)
    except Exception as e:  # noqa: BLE001
        add("An .xlsx file was produced and opens with openpyxl", False, f"{path.name}: {e}")
        return finish(run_dir, exp)
    add("An .xlsx file was produced and opens with openpyxl", True, path.name)

    with tempfile.TemporaryDirectory() as tmp:
        rc, msg = recalc(path, tmp)
        add("Excel opens the file and recalculates it", rc is not None, msg or "ok")
        wv = load_workbook(rc, data_only=True) if rc else None

    sheets = wf.worksheets
    data_sheets = [ws for ws in sheets if not NOTE_SHEET.search(ws.title)] or sheets[:1]

    # ---- style ---------------------------------------------------------- #
    heads, id_ok, id_detail = [], False, []
    for ws in data_sheets:
        hr = header_row_of(ws)
        if hr is None:
            continue
        heads.extend(c for c in ws[hr] if not cx._blank(c.value))
        if str(ws.cell(hr, 1).value).strip().upper() == "ID":
            ids, ok = [], True
            for r in range(hr + 1, ws.max_row + 1):
                v = ws.cell(r, 1).value
                label = ws.cell(r, 2).value
                if isinstance(v, bool) or not isinstance(v, int):
                    continue  # blank rows, total rows and notes under the table have no ID
                ids.append(v)
            ok = ids == list(range(1, len(ids) + 1)) and len(ids) > 0
            id_detail.append(f"{ws.title}: ids={ids[:8]}")
            id_ok = id_ok or ok
    add("A data sheet has an ID first column numbered 1..n", id_ok, "; ".join(id_detail) or "no ID header in column A")
    add("Header cells are bold", heads and all(c.font.b for c in heads),
        f"{sum(1 for c in heads if c.font.b)}/{len(heads)} bold")

    head_ids = {id(c) for c in heads}
    body_sizes, body_fonts = Counter(), Counter()
    for ws in data_sheets:
        hr0 = header_row_of(ws) or 0
        for row in ws.iter_rows(min_row=hr0 + 1):  # rows above the header are titles
            for c in row:
                if cx._blank(c.value) or id(c) in head_ids or type(c).__name__ == "MergedCell":
                    continue
                body_sizes[c.font.sz] += 1
                body_fonts[c.font.name] += 1
    size = body_sizes.most_common(1)[0][0] if body_sizes else None
    add("Body text is 10pt", size == 10, f"size distribution: {dict(body_sizes)}")
    font = body_fonts.most_common(1)[0][0] if body_fonts else None
    add("Body font is 맑은 고딕", font == "맑은 고딕", f"font distribution: {dict(body_fonts)}")

    fills = Counter()
    for c in heads:
        rgb = c.fill.fgColor.rgb if c.fill and c.fill.fill_type == "solid" else None
        if isinstance(rgb, str) and len(rgb) >= 6:
            fills[rgb[-6:].upper()] += 1
    ok_fill = fills and all(in_family(k, args.color) for k in fills)
    add(f"Header fill uses a {args.color} main color", ok_fill, f"header fills: {dict(fills)}")

    charts = [(ws.title, type(ch).__name__) for ws in sheets for ch in ws._charts]
    add("At least one chart exists", bool(charts), str(charts))

    # chart sanity: no chart on a sources sheet, no ID/rank series, rates not mixed with values
    rate_re = re.compile(r"rate|share|growth|yoy|%|비율|점유율|성장률|증감률|증가율|달성률", re.I)
    idlike_re = re.compile(r"^\s*(id|no\.?|#|번호|순위|rank)\s*$", re.I)
    problems = []
    for ws in sheets:
        for ch in ws._charts:
            if SOURCE_SHEET.match(ws.title):
                problems.append(f"chart on sources sheet '{ws.title}'")
            kinds = set()
            for ser in ch.series:
                name = None
                try:
                    ref = ser.tx.strRef.f
                    sh, cell = ref.rsplit("!", 1)
                    name = wf[sh.strip("'")][cell.replace("$", "")].value
                except Exception:  # noqa: BLE001
                    pass
                if name is None:
                    continue
                if idlike_re.match(str(name)):
                    problems.append(f"series '{name}' on '{ws.title}' is an ID/rank column")
                kinds.add("rate" if rate_re.search(str(name)) else "value")
            if len(kinds) > 1:
                problems.append(f"chart on '{ws.title}' mixes rate and value series")
    add("Charts are sensible (none on a sources sheet, no ID/rank series, rates not mixed with values)",
        not problems, problems or "ok")

    # ---- text of the whole workbook ------------------------------------ #
    texts = []
    for ws in sheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and not cx._is_formula(c.value):
                    texts.append(c.value)
    full = "\n".join(texts)
    hangul = len(re.findall(r"[가-힣]", full))
    letters = len(re.findall(r"[A-Za-z가-힣]", full)) or 1
    ratio = hangul / letters
    if args.lang == "ko":
        add("Text is written in Korean", ratio > 0.3, f"Hangul share = {ratio:.2f}")
    else:
        add("Text is written in English", ratio < 0.02, f"Hangul share = {ratio:.2f}")
    md = [t[:40] for t in texts if "**" in t or re.search(r"\[[^\]]+\]\(https?://", t)]
    add("No raw Markdown syntax in cells", not md, "clean" if not md else md[:3])

    if args.mode == "topic":
        names = [ws.title for ws in sheets]
        add("Has a summary sheet", any(re.search(r"^(요약|summary|overview)", n, re.I) for n in names), names)
        src = [ws for ws in sheets if SOURCE_SHEET.match(ws.title)]
        urls = set(re.findall(r"https?://[^\s)\]>,\"']+", "\n".join(
            str(c.value) for ws in src for row in ws.iter_rows() for c in row if c.value)))
        add("Has a sources sheet with at least 5 distinct URLs", bool(src) and len(urls) >= 5,
            f"{len(urls)} URLs on {[ws.title for ws in src]}")
        cites = re.findall(r"\[\d+\]", full)
        add("Uses [n] source markers at least 3 times", len(cites) >= 3, f"{len(cites)} markers")
        bad = []
        for ws in data_sheets:
            hr = header_row_of(ws)
            for row in ws.iter_rows(min_row=(hr or 0) + 1):
                for c in row:
                    if isinstance(c.value, str) and not cx._is_formula(c.value) and cx.to_number(c.value) is not None:
                        bad.append(f"{ws.title}!{c.coordinate}={c.value!r}")
        add("Numbers in data sheets are stored as numbers, not text", not bad, bad[:4] or "clean")
    else:
        if args.input and args.input_sha:
            now = hashlib.sha256(Path(args.input).read_bytes()).hexdigest()
            was = Path(args.input_sha).read_text().strip()
            add("The original input file is unchanged", now == was, f"sha256 {'matches' if now == was else 'DIFFERS'}")
        numbers = []
        if wv is not None:
            for ws in wv.worksheets:
                for row in ws.iter_rows():
                    for c in row:
                        if isinstance(c.value, (int, float)):
                            numbers.append(c.value)
        has_total = any(abs(n - 12580) < 0.5 for n in numbers) or bool(re.search(r"12,?580", full))
        add("The correct grand total 12,580 appears", has_total, "found" if has_total else "12,580 not found")
        mentions = re.search(r"(텍스트|문자|text)", full, re.I) and re.search(r"(부산|busan|1,?250)", full, re.I)
        add("Notes that Busan's August value is stored as text", bool(mentions), "mentioned" if mentions else "not mentioned")
        flags_wrong = bool(re.search(r"11,?330", full)) or any(abs(n - 11330) < 0.5 for n in numbers)
        add("Shows or mentions the file's understated total 11,330 next to the correct one",
            flags_wrong and has_total, f"11,330 present={flags_wrong}")
        regions = ["서울", "부산", "대구", "인천", "광주", "대전"]
        have = [r for r in regions if any(r in t for t in texts)]
        add("All six regions are kept in the workbook", len(have) == 6, f"found {have}")
        stray = []
        for ws in data_sheets:
            for row in ws.iter_rows():
                label = next((c.value for c in row if isinstance(c.value, str)), None)
                if label and cx.is_total_header(label):
                    first = row[0].value
                    if isinstance(first, (int, float)):
                        stray.append(f"{ws.title}: total row has ID {first}")
        add("Total/blank rows are not numbered with an ID", not stray, stray or "ok")

    finish(run_dir, exp)


def finish(run_dir, exp):
    passed = sum(e["passed"] for e in exp)
    total = len(exp)
    out = {"expectations": exp,
           "summary": {"passed": passed, "failed": total - passed, "total": total,
                       "pass_rate": round(passed / total, 2) if total else 0.0}}
    (Path(run_dir) / "grading.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{run_dir}: {passed}/{total}")
    for e in exp:
        print(("  PASS " if e["passed"] else "  FAIL ") + e["text"] + "  -- " + e["evidence"][:120])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
