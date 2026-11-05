"""Grade one topic-docx-report run by inspecting the produced .docx.

Usage: python check_outputs.py <run-dir> --color blue|red|green --lang ko|en

Reads <run-dir>/outputs/*.docx and writes <run-dir>/grading.json in the
format the skill-creator viewer expects (text / passed / evidence).
Style checks use the *effective* value (run override, else style chain), so a
document is judged by what Word would show, not by how it was built.
"""
import argparse
import colorsys
import json
import re
import sys
from collections import Counter
from pathlib import Path

from docx import Document

FONT = "맑은 고딕"
HUE_RANGES = {  # degrees on the HSV wheel
    "blue": [(190, 255)],
    "red": [(0, 18), (342, 360)],
    "green": [(80, 170)],
}


def style_chain(style):
    while style is not None:
        yield style
        style = style.base_style


def eff_size_pt(par):
    for run in par.runs:
        if run.font.size:
            return run.font.size.pt
    for st in style_chain(par.style):
        if st.font.size:
            return st.font.size.pt
    return 11.0  # Word default for the python-docx template


def eff_fonts(par):
    ascii_, east = None, None
    for run in par.runs:
        rf = run._r.rPr.rFonts if run._r.rPr is not None else None
        if rf is not None:
            ascii_ = ascii_ or rf.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii")
            east = east or rf.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia")
    for st in style_chain(par.style):
        rPr = st.element.rPr
        rf = rPr.rFonts if rPr is not None else None
        if rf is not None:
            w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            ascii_ = ascii_ or rf.get(w + "ascii")
            east = east or rf.get(w + "eastAsia")
    return ascii_, east


def eff_color(par):
    for run in par.runs:
        if run.font.color is not None and run.font.color.rgb is not None:
            return str(run.font.color.rgb)
    for st in style_chain(par.style):
        if st.font.color is not None and st.font.color.rgb is not None:
            return str(st.font.color.rgb)
    return None


def hue_of(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360, s, v


def in_family(hex_, family):
    h, s, v = hue_of(hex_)
    if s < 0.25:
        return False
    return any(lo <= h <= hi for lo, hi in HUE_RANGES[family])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--color", required=True, choices=HUE_RANGES)
    ap.add_argument("--lang", required=True, choices=("ko", "en"))
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    files = sorted((run_dir / "outputs").glob("*.docx"))
    exp = []

    def add(text, passed, evidence):
        exp.append({"text": text, "passed": bool(passed), "evidence": evidence})

    if not files:
        add("A .docx file was produced and opens with python-docx", False, "no .docx in outputs/")
        finish(run_dir, exp)
        return
    try:
        doc = Document(files[0])
    except Exception as e:  # noqa: BLE001
        add("A .docx file was produced and opens with python-docx", False, f"{files[0].name}: {e}")
        finish(run_dir, exp)
        return
    add("A .docx file was produced and opens with python-docx", True, files[0].name)

    pars = [p for p in doc.paragraphs if p.text.strip()]
    full = "\n".join(p.text for p in pars)
    for t in doc.tables:
        for row in t.rows:
            full += "\n" + " ".join(c.text for c in row.cells)

    # --- style: title ---
    title = next((p for p in pars if p.style.name == "Title"), pars[0] if pars else None)
    if title is not None:
        sz = eff_size_pt(title)
        add("Title is 40px (30pt)", abs(sz - 30) < 0.01, f"title paragraph '{title.text[:40]}' = {sz}pt")
    else:
        add("Title is 40px (30pt)", False, "no paragraphs")

    # --- style: body ---
    body = [p for p in pars if not p.style.name.startswith(("Heading", "Title", "Header", "Footer"))]
    sizes = Counter(eff_size_pt(p) for p in body)
    mode = sizes.most_common(1)[0][0] if sizes else None
    add("Body text is 14px (10.5pt)", mode is not None and abs(mode - 10.5) < 0.01,
        f"body size distribution (pt): {dict(sizes)}")

    # --- style: font ---
    probe = ([title] if title is not None else []) + body[:5]
    bad = []
    for p in probe:
        a, e = eff_fonts(p)
        if FONT not in (a, e):
            bad.append(f"'{p.text[:25]}' ascii={a} eastAsia={e}")
    add("Font is 맑은 고딕 for title and body", probe and not bad,
        "all probed paragraphs use 맑은 고딕" if not bad else "; ".join(bad[:3]))

    # --- style: main color ---
    heads = [p for p in pars if p.style.name.startswith(("Heading", "Title"))]
    colors = [eff_color(p) for p in heads]
    ok_colors = [c for c in colors if c and in_family(c, args.color)]
    add(f"Title and headings use a {args.color} main color",
        heads and len(ok_colors) == len(heads),
        f"heading colors: {Counter(colors).most_common(4)}")

    # --- structure ---
    n_head = len([p for p in pars if p.style.name.startswith("Heading")])
    add("Has at least 3 section headings", n_head >= 3, f"{n_head} Heading-style paragraphs")
    add("Has a summary section",
        any(re.search(r"요약|summary|executive", p.text, re.I) for p in pars
            if p.style.name.startswith("Heading")),
        "heading list: " + " | ".join(p.text for p in pars if p.style.name.startswith("Heading"))[:200])
    add("Has at least one table", len(doc.tables) >= 1, f"{len(doc.tables)} table(s)")

    # --- sources ---
    urls = set(re.findall(r"https?://[^\s)\]>,]+", full))
    add("Lists at least 5 distinct source URLs", len(urls) >= 5, f"{len(urls)} distinct URLs")
    cites = re.findall(r"\[\d+\]", "\n".join(p.text for p in pars))
    add("Uses inline [n] citations at least 3 times", len(cites) >= 3, f"{len(cites)} citation markers")

    # --- language ---
    hangul = len(re.findall(r"[가-힣]", full))
    letters = len(re.findall(r"[A-Za-z가-힣]", full)) or 1
    ratio = hangul / letters
    if args.lang == "ko":
        add("Report is written in Korean", ratio > 0.3, f"Hangul share of letters = {ratio:.2f}")
    else:
        add("Report is written in English", ratio < 0.02, f"Hangul share of letters = {ratio:.2f}")

    # --- hygiene ---
    md = [p.text[:40] for p in pars if "**" in p.text or "](" in p.text or re.match(r"#{1,4} ", p.text)]
    add("No raw Markdown syntax in the text", not md, "clean" if not md else f"found: {md[:3]}")
    empty = sum(1 for p in doc.paragraphs if not p.text.strip())
    add("No more empty paragraphs than tables (no stray blank lines)", empty <= len(doc.tables),
        f"{empty} empty paragraph(s), {len(doc.tables)} table(s)")

    finish(run_dir, exp)


def finish(run_dir, exp):
    passed = sum(e["passed"] for e in exp)
    total = len(exp)
    out = {
        "expectations": exp,
        "summary": {"passed": passed, "failed": total - passed, "total": total,
                    "pass_rate": round(passed / total, 2) if total else 0.0},
    }
    (Path(run_dir) / "grading.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{run_dir}: {passed}/{total}")
    for e in exp:
        print(("  PASS " if e["passed"] else "  FAIL ") + e["text"] + "  -- " + e["evidence"][:110])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
