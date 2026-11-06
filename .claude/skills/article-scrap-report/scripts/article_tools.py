#!/usr/bin/env python
"""Build a Word report and a PowerPoint deck from scraped-article data.

One JSON spec (articles + analysis) feeds both documents, so the report and the
deck always say the same thing.

Commands
  validate <spec.json>                      check the spec and the screenshot files
  docx     <spec.json> -o <out.docx>        build the report with python-docx
  pptx     <spec.json> -o <out.pptx> [--template t.pptx]
                                            build the deck with python-pptx; with --template the
                                            deck takes the template's look and keeps its credit slides
  read     <file.docx|file.pptx>            print the text of a finished file
  colors                                    list supported color names

Spec (all text is plain text, no Markdown):
{
  "title": "...", "subtitle": "...", "date": "2026-11-06", "lang": "ko",
  "color": "navy", "font": "맑은 고딕",
  "summary": ["fact [1]", ...],
  "themes": [{"heading": "...", "text": "..."}],
  "table": {"header": ["Article", "Publisher", "Key point"], "rows": [[...]]},
  "takeaways": ["..."],
  "articles": [{
      "title": "...", "publisher": "...", "date": "2026-11-06", "url": "https://...",
      "screenshot": "output/playwright/a1.png",
      "summary": ["point", "point"], "keywords": ["k1", "k2"]
  }]
}
Relative paths resolve against the spec file's folder, then the working directory.
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULTS = {"color": "1F4E79", "title_px": 40, "body_px": 14, "font": "맑은 고딕"}
PX_TO_PT = 0.75

NAMED_COLORS = {
    "red": "C00000", "빨강": "C00000", "blue": "2E75B6", "파랑": "2E75B6",
    "navy": "1F3864", "남": "1F3864", "green": "548235", "초록": "548235",
    "orange": "ED7D31", "주황": "ED7D31", "purple": "7030A0", "보라": "7030A0",
    "pink": "D6336C", "분홍": "D6336C", "teal": "008080", "청록": "008080",
    "skyblue": "5B9BD5", "하늘": "5B9BD5", "brown": "7F4F24", "갈": "7F4F24",
    "gray": "595959", "grey": "595959", "회": "595959", "black": "000000",
    "검정": "000000", "yellow": "BF9000", "노랑": "BF9000",
}

LABELS = {
    "ko": {"summary": "핵심 요약", "themes": "분석", "table": "기사 비교",
           "articles": "스크랩한 기사", "takeaways": "시사점", "sources": "출처",
           "date": "작성일", "scope": "스크랩 기사", "count": "건",
           "keywords": "키워드", "agenda": "목차"},
    "en": {"summary": "Summary", "themes": "Analysis", "table": "Article comparison",
           "articles": "Scraped articles", "takeaways": "Takeaways", "sources": "Sources",
           "date": "Prepared", "scope": "Articles", "count": "",
           "keywords": "Keywords", "agenda": "Agenda"},
}


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def parse_color(value):
    raw = str(value).strip()
    v = raw.lower().replace(" ", "")
    m = re.fullmatch(r"#?([0-9a-f]{6})", v)
    if m:
        return m.group(1).upper()
    for key in (v, v[:-1] if v.endswith("색") else v):
        if key in NAMED_COLORS:
            return NAMED_COLORS[key]
    sys.exit(f"unknown color: {raw!r}. Use HEX such as #1F4E79 or a name from `colors`.")


def tint(hex_color, share=0.12):
    rgb = [int(hex_color[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{round(c * share + 255 * (1 - share)):02X}" for c in rgb)


def text_on(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return "000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 160 else "FFFFFF"


def load_spec(path):
    p = Path(path)
    spec = json.loads(p.read_text(encoding="utf-8-sig"))
    spec["_base"] = p.resolve().parent
    spec["_color"] = parse_color(spec.get("color", DEFAULTS["color"]))
    spec["_font"] = spec.get("font", DEFAULTS["font"])
    spec["_lang"] = spec.get("lang", "ko") if spec.get("lang", "ko") in LABELS else "en"
    spec["_labels"] = LABELS[spec["_lang"]]
    if not spec.get("articles"):
        sys.exit("spec has no articles")
    return spec


def find_file(spec, rel):
    if not rel:
        return None
    p = Path(rel)
    for cand in ([p] if p.is_absolute() else [spec["_base"] / p, Path.cwd() / p]):
        if cand.exists():
            return cand
    return None


def cropped_image(spec, rel, aspect):
    """Full-page screenshots are very tall. Crop the top part to width:height = aspect
    and save next to the original as <name>_crop_<aspect>.png. Returns the path or None."""
    src = find_file(spec, rel)
    if src is None:
        return None
    from PIL import Image
    out = src.with_name(f"{src.stem}_crop_{aspect:.2f}.png")
    with Image.open(src) as im:
        w, h = im.size
        target_h = min(h, round(w / aspect))
        im.crop((0, 0, w, target_h)).save(out)
    return out


def sources(spec):
    return [f"{a['title']}, {a.get('publisher', '')} ({a.get('date', '')}). {a.get('url', '')}"
            for a in spec["articles"]]


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #
def cmd_validate(args):
    spec = load_spec(args.spec)
    problems = []
    for i, a in enumerate(spec["articles"], 1):
        for key in ("title", "publisher", "date", "url"):
            if not a.get(key):
                problems.append(f"article {i}: missing {key}")
        if not a.get("summary"):
            problems.append(f"article {i}: missing summary")
        if a.get("screenshot") and find_file(spec, a["screenshot"]) is None:
            problems.append(f"article {i}: screenshot not found: {a['screenshot']}")
        if not a.get("screenshot"):
            problems.append(f"article {i}: no screenshot (it will be skipped in both files)")
    n = len(spec["articles"])
    cited = {int(x) for t in spec.get("summary", []) + [t.get("text", "") for t in spec.get("themes", [])]
             for x in re.findall(r"\[(\d+)\]", t)}
    for c in sorted(cited):
        if c < 1 or c > n:
            problems.append(f"citation [{c}] has no matching article (1-{n})")
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print(f"ok: {n} articles, spec is consistent")


# --------------------------------------------------------------------------- #
# docx
# --------------------------------------------------------------------------- #
def cmd_docx(args):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    spec = load_spec(args.spec)
    font, color, L = spec["_font"], spec["_color"], spec["_labels"]
    title_px = args.title_px or spec.get("title_px", DEFAULTS["title_px"])
    body_px = args.body_px or spec.get("body_px", DEFAULTS["body_px"])
    pt = lambda px: Pt(px * PX_TO_PT)

    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2)

    def set_font(style, size, rgb=None, bold=None):
        style.font.name = font
        rfonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ("w:eastAsia", "w:cs"):
            rfonts.set(qn(attr), font)
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            rfonts.attrib.pop(qn(attr), None)
        style.font.size = size
        if rgb:
            style.font.color.rgb = RGBColor.from_string(rgb)
        if bold is not None:
            style.font.bold = bold

    set_font(doc.styles["Normal"], pt(body_px))
    doc.styles["Normal"].paragraph_format.line_spacing = 1.5
    doc.styles["Normal"].paragraph_format.space_after = Pt(6)
    set_font(doc.styles["Title"], pt(title_px), color, True)
    for bottom in doc.styles["Title"].element.xpath(".//w:pBdr/w:bottom"):
        bottom.set(qn("w:color"), color)
    for name, scale in (("Heading 1", 1.4), ("Heading 2", 1.2)):
        set_font(doc.styles[name], pt(body_px * scale), color, True)
        doc.styles[name].paragraph_format.space_before = Pt(18)
        doc.styles[name].paragraph_format.space_after = Pt(6)
    for name in ("List Bullet", "List Number"):
        set_font(doc.styles[name], pt(body_px))

    def shade(cell, fill):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)
        tcPr.append(shd)

    def add_table(header, rows):
        t = doc.add_table(rows=1 + len(rows), cols=len(header))
        t.style = "Table Grid"
        for r, row in enumerate([header] + rows):
            for c, text in enumerate(row):
                cell = t.cell(r, c)
                cell.text = ""
                run = cell.paragraphs[0].add_run(str(text))
                run.font.size = pt(body_px * 0.9)
                if r == 0:
                    run.bold = True
                    run.font.color.rgb = RGBColor.from_string(text_on(color))
                    shade(cell, color)
                elif r % 2 == 0:
                    shade(cell, tint(color))
        doc.add_paragraph()

    n = len(spec["articles"])
    doc.add_paragraph(spec["title"], style="Title")
    meta = f"{L['date']}: {spec.get('date', '')} · {L['scope']}: {n}{L['count']}"
    if spec.get("subtitle"):
        meta = spec["subtitle"] + " · " + meta
    doc.add_paragraph(meta)

    if spec.get("summary"):
        doc.add_heading(L["summary"], level=1)
        for s in spec["summary"]:
            doc.add_paragraph(s, style="List Bullet")

    if spec.get("themes"):
        doc.add_heading(L["themes"], level=1)
        for th in spec["themes"]:
            doc.add_heading(th["heading"], level=2)
            doc.add_paragraph(th["text"])

    tb = spec.get("table")
    if tb and tb.get("rows"):
        doc.add_heading(L["table"], level=1)
        add_table(tb["header"], tb["rows"])

    doc.add_heading(L["articles"], level=1)
    for i, a in enumerate(spec["articles"], 1):
        doc.add_heading(f"{i}. {a['title']}", level=2)
        p = doc.add_paragraph(f"{a.get('publisher', '')} · {a.get('date', '')} · {a.get('url', '')}")
        for r in p.runs:
            r.font.size = pt(body_px * 0.85)
            r.font.color.rgb = RGBColor.from_string("595959")
        shot = cropped_image(spec, a.get("screenshot"), 16 / 10)
        if shot:
            pic = doc.add_paragraph()
            pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pic.add_run().add_picture(str(shot), width=Cm(15))
        for s in a.get("summary", []):
            doc.add_paragraph(s, style="List Bullet")
        if a.get("keywords"):
            doc.add_paragraph(f"{L['keywords']}: " + ", ".join(a["keywords"]))

    if spec.get("takeaways"):
        doc.add_heading(L["takeaways"], level=1)
        for s in spec["takeaways"]:
            doc.add_paragraph(s, style="List Bullet")

    doc.add_heading(L["sources"], level=1)
    for s in sources(spec):
        doc.add_paragraph(s, style="List Number")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print(f"saved: {out}")


# --------------------------------------------------------------------------- #
# pptx
# --------------------------------------------------------------------------- #
def cmd_pptx(args):
    from lxml import etree
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Inches, Pt

    spec = load_spec(args.spec)
    if args.template:
        return cmd_pptx_template(args, spec)
    font, color, L = spec["_font"], spec["_color"], spec["_labels"]
    light = tint(color, 0.10)
    W, H = 13.333, 7.5

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    blank = prs.slide_layouts[6]

    def rgb(h):
        return RGBColor.from_string(h)

    def style_run(run, size, rgb_hex, bold=False):
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = rgb(rgb_hex)
        rPr = run._r.get_or_add_rPr()
        for tag in ("a:ea", "a:cs"):
            el = etree.SubElement(rPr, qn(tag))
            el.set("typeface", font)

    def rect(slide, x, y, w, h, fill):
        shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(fill)
        shp.line.fill.background()
        return shp

    def text(slide, x, y, w, h, lines, size, rgb_hex="222222", bold=False, bullet=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, space=6):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        lines = [lines] if isinstance(lines, str) else lines
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            p.space_after = Pt(space)
            run = p.add_run()
            run.text = ("• " + line) if bullet else line
            style_run(run, size, rgb_hex, bold)
        return box

    page = {"n": 0}

    def new_slide(heading):
        s = prs.slides.add_slide(blank)
        page["n"] += 1
        rect(s, 0, 0, W, 1.1, color)
        text(s, 0.6, 0.12, W - 1.2, 0.86, heading, 30, text_on(color), True, anchor=MSO_ANCHOR.MIDDLE)
        text(s, W - 1.2, H - 0.5, 0.8, 0.35, str(page["n"] + 1), 11, "808080", align=PP_ALIGN.RIGHT)
        return s

    n = len(spec["articles"])

    # 1. Title slide
    s = prs.slides.add_slide(blank)
    rect(s, 0, 0, W, H, color)
    rect(s, 0.8, 4.05, 2.2, 0.06, text_on(color))
    text(s, 0.8, 2.0, W - 1.6, 2.0, spec["title"], spec.get("title_px", DEFAULTS["title_px"]) * PX_TO_PT,
         text_on(color), True, anchor=MSO_ANCHOR.BOTTOM)
    sub = f"{spec.get('subtitle', '')}  {L['date']}: {spec.get('date', '')} · {L['scope']}: {n}{L['count']}".strip()
    text(s, 0.8, 4.3, W - 1.6, 1.0, sub, 18, text_on(color))

    # 2. Summary
    if spec.get("summary"):
        s = new_slide(L["summary"])
        text(s, 0.8, 1.5, W - 1.6, H - 2.2, spec["summary"], 22, bullet=True, space=14)

    # 3. Themes (one per slide)
    for th in spec.get("themes", []):
        s = new_slide(th["heading"])
        rect(s, 0.8, 1.6, 0.08, 3.0, color)
        text(s, 1.1, 1.5, W - 2.0, H - 2.3, th["text"], 22)

    # 4. Comparison table
    tb = spec.get("table")
    if tb and tb.get("rows"):
        s = new_slide(L["table"])
        rows, cols = len(tb["rows"]) + 1, len(tb["header"])
        gf = s.shapes.add_table(rows, cols, Inches(0.6), Inches(1.5), Inches(W - 1.2),
                                Inches(min(0.6 * rows, H - 2.2)))
        for r, row in enumerate([tb["header"]] + tb["rows"]):
            for c, val in enumerate(row):
                cell = gf.table.cell(r, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(color if r == 0 else (tint(color) if r % 2 == 0 else "FFFFFF"))
                tf = cell.text_frame
                tf.word_wrap = True
                run = tf.paragraphs[0].add_run()
                run.text = str(val)
                style_run(run, 14, text_on(color) if r == 0 else "222222", r == 0)

    # 5. One slide per article: screenshot left, summary right
    for i, a in enumerate(spec["articles"], 1):
        s = new_slide(f"{i}. {a['title']}")
        shot = cropped_image(spec, a.get("screenshot"), 6.2 / 5.2)
        if shot:
            s.shapes.add_picture(str(shot), Inches(0.6), Inches(1.4), width=Inches(6.2))
        x = 7.1 if shot else 0.8
        w = W - x - 0.6
        text(s, x, 1.4, w, 0.5, f"{a.get('publisher', '')} · {a.get('date', '')}", 14, "595959")
        text(s, x, 1.95, w, 3.6, a.get("summary", []), 18, bullet=True, space=10)
        if a.get("keywords"):
            text(s, x, 5.7, w, 0.6, f"{L['keywords']}: " + ", ".join(a["keywords"]), 14, color, True)
        text(s, x, 6.4, w, 0.5, a.get("url", ""), 10, "808080")

    # 6. Takeaways
    if spec.get("takeaways"):
        s = new_slide(L["takeaways"])
        text(s, 0.8, 1.5, W - 1.6, H - 2.2, spec["takeaways"], 22, bullet=True, space=14)

    # 7. Sources
    s = new_slide(L["sources"])
    text(s, 0.8, 1.4, W - 1.6, H - 2.0, [f"[{i}] {t}" for i, t in enumerate(sources(spec), 1)], 13, space=8)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    print(f"saved: {out} ({len(prs.slides)} slides)")


# --------------------------------------------------------------------------- #
# pptx with a template file (--template)
# --------------------------------------------------------------------------- #
# Values read from minimalist-white-slides.pptx (SlidesCarnival): cream background,
# one red accent for titles and rules, a 3pt rule near the bottom, three small header
# texts at the top, a 56pt title and 18pt body on a 20 x 11.25 inch canvas.
TEMPLATE_STYLE = {
    "bg": "FFFCF9", "accent": "C03221", "text": "2B2B2B", "muted": "7A6A66",
    "head_font": "DM Serif Display", "body_font": "맑은 고딕",
}


def fit_font_size(paragraphs, width_in, height_in, base, minimum, line_gap=1.35, para_gap_pt=10):
    """Largest font size (pt) in [minimum, base] whose estimated wrapped height fits the box.
    Korean characters count as one em wide, Latin ones as 0.55 em."""
    size = base
    while size > minimum:
        total = 0.0
        for para in paragraphs:
            lines, cur, maxw = 1, 0.0, width_in * 72
            for ch in para:
                w = size * (1.0 if ord(ch) >= 0x2E80 else 0.55)
                if cur + w > maxw:
                    lines, cur = lines + 1, w
                else:
                    cur += w
            total += lines * size * line_gap + para_gap_pt
        if total <= height_in * 72:
            break
        size -= 1
    return size


def cmd_pptx_template(args, spec):
    from lxml import etree
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Inches, Pt

    if args.template_style == "reference":
        return cmd_pptx_reference(args, spec)
    st, L = TEMPLATE_STYLE, spec["_labels"]
    tpl = Path(args.template)
    if not tpl.exists():
        sys.exit(f"template not found: {tpl}")
    prs = Presentation(tpl)
    W, H = prs.slide_width / 914400, prs.slide_height / 914400

    # Keep the template's closing slides (resource page and credits): the license asks
    # users to keep the attribution. Everything before them is replaced by new slides.
    id_list = prs.slides._sldIdLst
    ids = list(id_list)
    if len(ids) <= args.keep_last:
        sys.exit(f"template has only {len(ids)} slides; cannot keep the last {args.keep_last}")
    keep = ids[-args.keep_last:]
    kept_text = " ".join(sh.text_frame.text
                         for i in range(len(ids) - args.keep_last, len(ids))
                         for sh in prs.slides[i].shapes if sh.has_text_frame)
    if not re.search(r"credit|resource", kept_text, re.I):
        print("warning: the kept slides do not mention 'credit' or 'resource'; check --keep-last",
              file=sys.stderr)
    for sid in ids[:-args.keep_last]:
        prs.part.drop_rel(sid.rId)
        id_list.remove(sid)

    blank = next((l for l in prs.slide_layouts if l.name.upper() == "BLANK"), prs.slide_layouts[0])
    rgb = RGBColor.from_string
    page = {"n": 0}

    def run_style(run, size, color, bold=False, head=False):
        run.font.name = st["head_font"] if head else st["body_font"]
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = rgb(color)
        rPr = run._r.get_or_add_rPr()
        for tag in ("a:ea", "a:cs"):  # Korean text needs an East Asian font
            el = etree.SubElement(rPr, qn(tag))
            el.set("typeface", st["body_font"])

    def text(slide, x, y, w, h, paras, size, color, bold=False, head=False, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP, bullet=False, space=10, spacing=1.0):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        paras = [paras] if isinstance(paras, str) else paras
        for i, para in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            p.space_after = Pt(space)
            p.line_spacing = spacing
            r = p.add_run()
            r.text = ("• " + para) if bullet else para
            run_style(r, size, color, bold, head)
        return box

    def rule(slide):
        line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(1.125), Inches(10.125),
                                          Inches(W - 1.125), Inches(10.125))
        line.line.color.rgb = rgb(st["accent"])
        line.line.width = Pt(3)

    def new_slide(chrome=True):
        s = prs.slides.add_slide(blank)
        page["n"] += 1
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = rgb(st["bg"])
        if chrome:
            text(s, 1.1, 0.4, 6.0, 0.4, spec.get("subtitle", ""), 12, st["accent"], head=True)
            text(s, 7.0, 0.4, 6.0, 0.4, spec["title"], 12, st["accent"], head=True, align=PP_ALIGN.CENTER)
            text(s, 12.9, 0.4, 6.0, 0.4, spec.get("date", ""), 12, st["accent"], head=True, align=PP_ALIGN.RIGHT)
            rule(s)
            text(s, W - 3.1, 10.3, 2.0, 0.4, str(page["n"]), 12, st["accent"], head=True, align=PP_ALIGN.RIGHT)
        return s

    def heading(slide, label):
        text(slide, 1.1, 1.3, W - 2.2, 1.5, label, 56, st["accent"], head=True, spacing=0.9)

    def bullet_slide(label, items, base=26):
        s = new_slide()
        heading(s, label)
        size = fit_font_size(items, W - 2.2, 6.0, base, 16)
        text(s, 1.1, 3.3, W - 2.2, 6.5, items, size, st["text"], bullet=True, space=14)
        return s

    n = len(spec["articles"])

    # Cover
    s = new_slide(chrome=False)
    title_size = fit_font_size([spec["title"]], W - 2.2, 3.4, 88, 40, line_gap=1.05, para_gap_pt=0)
    text(s, 1.1, 3.4, W - 2.2, 3.6, spec["title"], title_size, st["accent"], head=True, spacing=0.85)
    sub = f"{spec.get('subtitle', '')}  ·  {L['date']}: {spec.get('date', '')}  ·  {L['scope']}: {n}{L['count']}"
    text(s, 1.1, 7.4, W - 2.2, 0.8, sub.strip(" ·"), 22, st["muted"])
    rule(s)

    if spec.get("summary"):
        bullet_slide(L["summary"], spec["summary"])

    for th in spec.get("themes", []):
        s = new_slide()
        size = fit_font_size([th["heading"]], W - 2.2, 2.0, 48, 28, line_gap=1.1, para_gap_pt=0)
        text(s, 1.1, 1.3, W - 2.2, 2.2, th["heading"], size, st["accent"], head=True, spacing=0.9)
        body = fit_font_size([th["text"]], W - 2.2, 5.6, 26, 16)
        text(s, 1.1, 4.0, W - 2.2, 5.8, th["text"], body, st["text"], spacing=1.1)

    tb = spec.get("table")
    if tb and tb.get("rows"):
        s = new_slide()
        heading(s, L["table"])
        rows, cols = len(tb["rows"]) + 1, len(tb["header"])
        gf = s.shapes.add_table(rows, cols, Inches(1.1), Inches(3.3), Inches(W - 2.2),
                                Inches(min(1.0 * rows, 6.4)))
        tint_fill = tint(st["accent"], 0.07)
        for r, row in enumerate([tb["header"]] + tb["rows"]):
            for c, val in enumerate(row):
                cell = gf.table.cell(r, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(st["accent"] if r == 0 else (tint_fill if r % 2 == 0 else st["bg"]))
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.text_frame.word_wrap = True
                run = cell.text_frame.paragraphs[0].add_run()
                run.text = str(val)
                run_style(run, 18, "FFFFFF" if r == 0 else st["text"], bold=(r == 0))

    # One slide per article: text left, screenshot right (like the template's picture slide)
    for i, a in enumerate(spec["articles"], 1):
        s = new_slide()
        shot = cropped_image(spec, a.get("screenshot"), 8.9 / 8.6)  # ends above the bottom rule
        tw = 8.3 if shot else W - 2.2
        t_size = fit_font_size([f"{i}. {a['title']}"], tw, 3.0, 40, 24, line_gap=1.15, para_gap_pt=0)
        text(s, 1.1, 1.3, tw, 3.2, f"{i}. {a['title']}", t_size, st["accent"], head=True, spacing=0.95)
        text(s, 1.1, 4.6, tw, 0.4, f"{a.get('publisher', '')}  ·  {a.get('date', '')}", 14, st["muted"])
        bsize = fit_font_size(a.get("summary", []), tw, 3.9, 20, 13, para_gap_pt=8)
        text(s, 1.1, 5.1, tw, 4.0, a.get("summary", []), bsize, st["text"], bullet=True, space=8)
        if a.get("keywords"):
            text(s, 1.1, 9.15, tw, 0.4, f"{L['keywords']}: " + ", ".join(a["keywords"]), 14, st["accent"], bold=True)
        text(s, 1.1, 9.6, tw, 0.35, a.get("url", ""), 9, st["muted"])
        if shot:
            s.shapes.add_picture(str(shot), Inches(10.0), Inches(1.1), width=Inches(8.9))

    if spec.get("takeaways"):
        bullet_slide(L["takeaways"], spec["takeaways"])

    srcs = [f"[{i}] {t}" for i, t in enumerate(sources(spec), 1)]
    s = new_slide()
    heading(s, L["sources"])
    text(s, 1.1, 3.3, W - 2.2, 6.5, srcs, fit_font_size(srcs, W - 2.2, 6.2, 18, 11, para_gap_pt=8),
         st["text"], space=8)

    # Move the kept template slides (credits) behind the new ones
    for el in keep:
        id_list.remove(el)
        id_list.append(el)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    print(f"saved: {out} ({len(prs.slides)} slides, last {args.keep_last} are the template's credit slides)")


# --------------------------------------------------------------------------- #
# pptx in the look of references/이레퍼런스.pptx (--template-style reference)
# --------------------------------------------------------------------------- #
# Values read from that deck: steel-blue accent 7CA0BB, dark blue 214058, text 212121,
# gradient background E6EEF4 -> FFFFFF, a header bar (picture) with a dark label at the
# top-left, a skyline picture on the cover and closing slides, 20 x 11.25 inch canvas.
REFERENCE_STYLE = {
    "accent": "7CA0BB", "dark": "214058", "text": "212121", "muted": "595959",
    "grad_from": "E6EEF4", "grad_to": "FFFFFF", "card_line": "D5E1EB",
    "font": "맑은 고딕",
}


def cmd_pptx_reference(args, spec):
    import io
    from lxml import etree
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Inches, Pt

    st, L = REFERENCE_STYLE, spec["_labels"]
    tpl = Path(args.template)
    if not tpl.exists():
        sys.exit(f"template not found: {tpl}")
    prs = Presentation(tpl)
    W, H = prs.slide_width / 914400, prs.slide_height / 914400
    rgb = RGBColor.from_string

    def pic(slide_no, name):
        for sh in prs.slides[slide_no - 1].shapes:
            if sh.name == name and sh.shape_type == 13:
                return sh.image.blob
        sys.exit(f"template picture not found: slide {slide_no} {name}")

    art = {"skyline": pic(1, "Picture 2"), "bar": pic(3, "Picture 3"), "label": pic(3, "Picture 4"),
           "end_skyline": pic(14, "Picture 2")}

    id_list = prs.slides._sldIdLst
    for sid in list(id_list):  # the template's own slides are replaced
        prs.part.drop_rel(sid.rId)
        id_list.remove(sid)
    blank = next((l for l in prs.slide_layouts if l.name.upper() == "BLANK"), prs.slide_layouts[0])
    page = {"n": 0}

    def run_style(run, size, color, bold=False):
        run.font.name = st["font"]
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = rgb(color)
        rPr = run._r.get_or_add_rPr()
        for tag in ("a:ea", "a:cs"):
            etree.SubElement(rPr, qn(tag)).set("typeface", st["font"])

    def text(slide, x, y, w, h, paras, size, color, bold=False, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP, bullet=False, space=10, spacing=1.0):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        paras = [paras] if isinstance(paras, str) else paras
        for i, para in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            p.space_after = Pt(space)
            p.line_spacing = spacing
            r = p.add_run()
            r.text = ("• " + para) if bullet else para
            run_style(r, size, color, bold)
        return box

    def picture(slide, key, x, y, w, h=None):
        kw = {"width": Inches(w)}
        if h:
            kw["height"] = Inches(h)
        return slide.shapes.add_picture(io.BytesIO(art[key]), Inches(x), Inches(y), **kw)

    def card(slide, x, y, w, h):
        shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        shp.adjustments[0] = 0.04
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb("FFFFFF")
        shp.line.color.rgb = rgb(st["card_line"])
        shp.line.width = Pt(1.5)
        shp.shadow.inherit = False
        return shp

    def pill(slide, cx, y, label, size=20):
        w = max(4.4, len(label) * size / 72 * 0.9 + 1.0)
        shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(cx - w / 2), Inches(y), Inches(w), Inches(0.65))
        shp.adjustments[0] = 0.5
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(st["accent"])
        shp.line.fill.background()
        shp.shadow.inherit = False
        tf = shp.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = label
        run_style(r, size, "FFFFFF", True)
        return shp

    def gradient_bg(slide):
        bg = slide.background.fill
        bg.gradient()
        bg.gradient_angle = 90
        stops = bg.gradient_stops
        stops[0].color.rgb = rgb(st["grad_from"])
        stops[0].position = 0
        stops[1].color.rgb = rgb(st["grad_to"])
        stops[1].position = 1

    label = spec.get("subtitle", "") or spec["title"]

    def new_slide(section):
        s = prs.slides.add_slide(blank)
        page["n"] += 1
        gradient_bg(s)
        picture(s, "bar", 0.39, 0.35, 19.22, 0.65)
        picture(s, "label", 0.39, 0.35, 2.64, 0.65)
        text(s, 0.39, 0.45, 2.64, 0.45, spec["title"][:10], 17, "FEFCF8", True, align=PP_ALIGN.CENTER)
        text(s, 7.2, 0.46, 12.0, 0.4, f"{spec['title']}   |   {section}", 17, st["dark"], align=PP_ALIGN.RIGHT)
        text(s, 0.6, 10.5, 18.8, 0.4, f"{label}   ·   {page['n']}", 13, st["accent"], align=PP_ALIGN.CENTER)
        return s

    def heading(slide, txt):
        size = fit_font_size([txt], W - 2.0, 1.2, 45, 28, line_gap=1.1, para_gap_pt=0)
        text(slide, 1.0, 1.35, W - 2.0, 1.2, txt, size, st["text"], True, align=PP_ALIGN.CENTER)

    def bullet_slide(section, items, base=28):
        s = new_slide(section)
        heading(s, section)
        card(s, 0.75, 2.8, W - 1.5, 7.4)
        size = fit_font_size(items, W - 3.0, 6.4, base, 16)
        text(s, 1.5, 3.2, W - 3.0, 6.6, items, size, st["text"], bullet=True, space=16)
        return s

    n = len(spec["articles"])

    # Cover
    s = prs.slides.add_slide(blank)
    page["n"] += 1
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = rgb("FFFFFF")
    picture(s, "skyline", -0.68, 7.24, 20.94, 4.03)
    text(s, 1.0, 1.5, W - 2.0, 0.5, label.upper(), 20, st["muted"], align=PP_ALIGN.CENTER)
    size = fit_font_size([spec["title"]], W - 2.4, 3.0, 85, 40, line_gap=1.1, para_gap_pt=0)
    text(s, 1.2, 2.3, W - 2.4, 3.0, spec["title"], size, st["accent"], True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 1.2, 5.4, W - 2.4, 0.7, f"{L['date']}: {spec.get('date', '')}  ·  {L['scope']}: {n}{L['count']}",
         30, st["text"], True, align=PP_ALIGN.CENTER)
    pill(s, W / 2, 6.35, label)

    if spec.get("summary"):
        bullet_slide(L["summary"], spec["summary"])

    for th in spec.get("themes", []):
        s = new_slide(L["summary"])
        heading(s, th["heading"])
        card(s, 0.75, 2.8, W - 1.5, 7.4)
        size = fit_font_size([th["text"]], W - 3.0, 6.4, 30, 16)
        text(s, 1.5, 3.3, W - 3.0, 6.6, th["text"], size, st["text"], spacing=1.2)

    tb = spec.get("table")
    if tb and tb.get("rows"):
        s = new_slide(L["table"])
        heading(s, L["table"])
        rows, cols = len(tb["rows"]) + 1, len(tb["header"])
        gf = s.shapes.add_table(rows, cols, Inches(0.75), Inches(2.9), Inches(W - 1.5), Inches(min(1.1 * rows, 7.2)))
        for r, row in enumerate([tb["header"]] + tb["rows"]):
            for c, val in enumerate(row):
                cell = gf.table.cell(r, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(st["dark"] if r == 0 else (st["grad_from"] if r % 2 == 0 else "FFFFFF"))
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.text_frame.word_wrap = True
                run = cell.text_frame.paragraphs[0].add_run()
                run.text = str(val)
                run_style(run, 18, "FFFFFF" if r == 0 else st["text"], bold=(r == 0))

    for i, a in enumerate(spec["articles"], 1):
        s = new_slide(f"{L['sources']} {i}" if False else f"ARTICLE {i:02d}")
        shot = cropped_image(spec, a.get("screenshot"), 8.7 / 7.4)
        card(s, 0.75, 2.8, 9.2 if shot else W - 1.5, 7.4)
        tw = 8.2 if shot else W - 2.5
        text(s, 1.1, 3.0, tw, 0.5, f"ARTICLE {i:02d}", 20, st["accent"], True)
        t_size = fit_font_size([a["title"]], tw, 1.7, 32, 22, line_gap=1.15, para_gap_pt=0)
        text(s, 1.1, 3.5, tw, 1.7, a["title"], t_size, st["text"], True, spacing=0.95)
        text(s, 1.1, 5.3, tw, 0.4, f"{a.get('publisher', '')}  ·  {a.get('date', '')}", 15, st["muted"])
        bsize = fit_font_size(a.get("summary", []), tw, 3.3, 22, 14, para_gap_pt=8)
        text(s, 1.1, 5.85, tw, 3.4, a.get("summary", []), bsize, st["text"], bullet=True, space=8)
        if a.get("keywords"):
            text(s, 1.1, 9.3, tw, 0.4, f"{L['keywords']}: " + ", ".join(a["keywords"]), 15, st["dark"], True)
        text(s, 1.1, 9.75, tw, 0.35, a.get("url", ""), 9, st["muted"])
        if shot:
            s.shapes.add_picture(str(shot), Inches(10.3), Inches(2.8), width=Inches(8.7))

    if spec.get("takeaways"):
        bullet_slide(L["takeaways"], spec["takeaways"])

    srcs = [f"[{i}] {t}" for i, t in enumerate(sources(spec), 1)]
    s = new_slide(L["sources"])
    heading(s, L["sources"])
    card(s, 0.75, 2.8, W - 1.5, 7.4)
    text(s, 1.5, 3.2, W - 3.0, 6.6, srcs, fit_font_size(srcs, W - 3.0, 6.4, 20, 11, para_gap_pt=8),
         st["text"], space=8)

    # Closing
    s = prs.slides.add_slide(blank)
    gradient_bg(s)
    picture(s, "end_skyline", -1.12, 5.5, 21.76, 7.21)
    closing = "감사합니다" if spec["_lang"] == "ko" else "Thank you"
    text(s, 0.94, 1.6, W - 2.0, 2.0, closing, 70, st["text"], True)
    text(s, 0.94, 3.9, W - 2.0, 1.0, f"{label}  ·  {spec.get('date', '')}", 23, st["text"])
    pill(s, 3.3, 5.0, spec.get("source_label", "news.naver.com"))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    print(f"saved: {out} ({len(prs.slides)} slides, reference style)")


# --------------------------------------------------------------------------- #
# read / colors
# --------------------------------------------------------------------------- #
def cmd_read(args):
    p = Path(args.file)
    if p.suffix.lower() == ".docx":
        from docx import Document
        doc = Document(p)
        for para in doc.paragraphs:
            if para.text.strip():
                print(f"[{para.style.name}] {para.text}")
        for i, t in enumerate(doc.tables, 1):
            print(f"--- table {i} ---")
            for row in t.rows:
                print(" | ".join(c.text for c in row.cells))
        print(f"inline images: {len(doc.inline_shapes)}")
    elif p.suffix.lower() == ".pptx":
        from pptx import Presentation
        prs = Presentation(p)
        for i, slide in enumerate(prs.slides, 1):
            print(f"--- slide {i} ---")
            for shp in slide.shapes:
                if shp.has_text_frame and shp.text_frame.text.strip():
                    print(shp.text_frame.text.replace("\n", " / "))
                elif shp.shape_type == 13:
                    print("[picture]")
                elif getattr(shp, "has_table", False) and shp.has_table:
                    for row in shp.table.rows:
                        print(" | ".join(c.text for c in row.cells))
    else:
        sys.exit("read supports .docx and .pptx")


def cmd_colors(_args):
    for k, v in NAMED_COLORS.items():
        print(f"{k:8} #{v}")


def main():
    # Windows consoles default to cp949, which garbles Korean and rejects bullets.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate")
    p.add_argument("spec")
    p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("docx")
    p.add_argument("spec")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--title-px", type=float)
    p.add_argument("--body-px", type=float)
    p.set_defaults(fn=cmd_docx)
    p = sub.add_parser("pptx")
    p.add_argument("spec")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--template", help="a .pptx template; its last slides (credits) are kept")
    p.add_argument("--template-style", choices=["slidescarnival", "reference"], default="slidescarnival",
                   help="'reference' reproduces the look of references/이레퍼런스.pptx and drops all template slides")
    p.add_argument("--keep-last", type=int, default=1,
                   help="template slides to keep at the end (default 1: the credits slide)")
    p.set_defaults(fn=cmd_pptx)
    p = sub.add_parser("read")
    p.add_argument("file")
    p.set_defaults(fn=cmd_read)
    p = sub.add_parser("colors")
    p.set_defaults(fn=cmd_colors)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
