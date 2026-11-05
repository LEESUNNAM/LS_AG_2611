"""Command-line helpers for Word documents, built on python-docx.

Defaults: title 40px, body 20px, font 맑은 고딕, main color 1F4E79.
(Word uses points: 1px = 0.75pt, so 40px = 30pt and 20px = 15pt.)

Commands:
  create   Build a new .docx from a JSON content file.
  read     Print paragraphs (with style) and tables of a .docx.
  replace  Find and replace text, keeping run formatting where possible.
  append   Append paragraphs to the end of an existing .docx.
  restyle  Re-apply font, sizes and main color to an existing .docx.
  colors   List the color names that --color understands.

Style options (create / restyle; the command line overrides the JSON file):
  --color     main color: a name (red, blue, 빨강, 파랑 ...) or HEX (#1F4E79)
  --title-px  title size in px (default 40)
  --body-px   body size in px (default 20)
  --font      font name (default 맑은 고딕)
  The main color is used for the title, headings, table header and borders.

Examples:
  python scripts/docx_tools.py create scripts/examples/sample_content.json -o output/doc.docx --color blue
  python scripts/docx_tools.py create content.json -o out.docx --color "#C00000" --no-footer
  python scripts/docx_tools.py restyle old.docx -o new.docx --color 초록
  python scripts/docx_tools.py read output/doc.docx
  python scripts/docx_tools.py replace output/doc.docx "old" "new" -o output/doc2.docx
  python scripts/docx_tools.py append output/doc.docx "More text" -o output/doc3.docx
  python scripts/docx_tools.py colors

JSON content format (blocks are written in order; style keys are optional):
  {
    "title": "Document title",
    "color": "navy", "title_px": 40, "body_px": 20, "font": "맑은 고딕",
    "author": "name",
    "blocks": [
      {"type": "heading", "text": "Section", "level": 1},
      {"type": "paragraph", "text": "Body text"},
      {"type": "bullets", "items": ["a", "b"]},
      {"type": "numbered", "items": ["first", "second"]},
      {"type": "table", "rows": [["h1", "h2"], ["c1", "c2"]], "header": true},
      {"type": "image", "path": "logo.png", "width_cm": 12},
      {"type": "page_break"}
    ]
  }
  Image paths are resolved relative to the JSON file, then the current folder.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

DEFAULTS = {"color": "1F4E79", "title_px": 40, "body_px": 14, "font": "맑은 고딕"}
PX_TO_PT = 0.75
# Heading sizes as a multiple of the body size (20px body -> 28/24/22px).
HEADING_SCALE = {"Heading 1": 1.4, "Heading 2": 1.2, "Heading 3": 1.1}
LINE_SPACING = 1.5
ZEBRA_TINT = 0.12  # share of the main color mixed into white for alternate rows

NAMED_COLORS = {
    "red": "C00000", "빨강": "C00000", "빨간": "C00000",
    "blue": "2E75B6", "파랑": "2E75B6", "파란": "2E75B6",
    "navy": "1F3864", "남": "1F3864",
    "green": "548235", "초록": "548235", "녹": "548235",
    "orange": "ED7D31", "주황": "ED7D31",
    "yellow": "BF9000", "노랑": "BF9000", "노란": "BF9000",
    "purple": "7030A0", "보라": "7030A0",
    "pink": "D6336C", "분홍": "D6336C",
    "teal": "008080", "청록": "008080",
    "skyblue": "5B9BD5", "하늘": "5B9BD5",
    "brown": "7F4F24", "갈": "7F4F24",
    "gray": "595959", "grey": "595959", "회": "595959",
    "black": "000000", "검정": "000000", "검은": "000000",
}
KO_LABEL = {"빨강", "파랑", "남", "초록", "주황", "노랑", "보라", "분홍", "청록",
            "하늘", "갈", "회", "검정"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def parse_color(value):
    """Return an uppercase 6-digit HEX string for a color name or HEX value."""
    raw = str(value).strip()
    v = raw.lower().replace(" ", "")
    m = re.fullmatch(r"#?([0-9a-f]{6})", v)
    if m:
        return m.group(1).upper()
    m = re.fullmatch(r"#?([0-9a-f]{3})", v)
    if m:
        return "".join(ch * 2 for ch in m.group(1)).upper()
    for key in (v, v[:-1] if v.endswith("색") else v):
        if key in NAMED_COLORS:
            return NAMED_COLORS[key]
    sys.exit(f"unknown color: {raw!r}. Use a HEX value such as #1F4E79 or a name "
             f"from `colors` (e.g. red, blue, 빨강, 파랑).")


def tint(hex_color, share=ZEBRA_TINT):
    """Mix a color into white; share is the amount of the color kept."""
    rgb = [int(hex_color[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{round(c * share + 255 * (1 - share)):02X}" for c in rgb)


def text_on(hex_color):
    """White text on dark fills, black on light fills."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return "000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 160 else "FFFFFF"


def rgb(hex_color):
    return RGBColor.from_string(hex_color)


def pt(px):
    return Pt(px * PX_TO_PT)


def resolve_settings(args, content=None):
    content = content or {}
    st = {}
    for key, default in DEFAULTS.items():
        cli = getattr(args, key, None)
        st[key] = cli if cli is not None else content.get(key, default)
    st["color"] = parse_color(st["color"])
    st["title_px"] = float(st["title_px"])
    st["body_px"] = float(st["body_px"])
    return st


def set_style_font(style, font, size, color=None, bold=None):
    style.font.name = font
    rfonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in ("w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), font)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rfonts.attrib.pop(qn(attr), None)  # theme fonts would override the name
    style.font.size = size
    if color:
        style.font.color.rgb = rgb(color)
    if bold is not None:
        style.font.bold = bold


def apply_styles(doc, st):
    font, color = st["font"], st["color"]
    body = st["body_px"]

    normal = doc.styles["Normal"]
    set_style_font(normal, font, pt(body))
    normal.paragraph_format.line_spacing = LINE_SPACING
    normal.paragraph_format.space_after = Pt(6)

    title = doc.styles["Title"]
    set_style_font(title, font, pt(st["title_px"]), color, bold=True)
    for bottom in title.element.xpath(".//w:pBdr/w:bottom"):
        bottom.set(qn("w:color"), color)  # default template draws a blue rule

    for name, scale in HEADING_SCALE.items():
        h = doc.styles[name]
        set_style_font(h, font, pt(body * scale), color, bold=True)
        h.paragraph_format.space_before = Pt(18)
        h.paragraph_format.space_after = Pt(6)

    for name in ("List Bullet", "List Number"):
        set_style_font(doc.styles[name], font, pt(body))
    for name in ("Header", "Footer"):
        if name in [s.name for s in doc.styles]:
            set_style_font(doc.styles[name], font, Pt(9), "595959")


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def set_table_borders(table, color):
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    look = tblPr.find(qn("w:tblLook"))  # keep schema order: borders before tblLook
    if look is not None:
        look.addprevious(borders)
    else:
        tblPr.append(borders)


def style_table(table, color, header=True):
    set_table_borders(table, color)
    zebra = tint(color)
    for r, row in enumerate(table.rows):
        for cell in row.cells:
            if header and r == 0:
                shade(cell, color)
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.bold = True
                        run.font.color.rgb = rgb(text_on(color))
            elif r % 2 == 0:
                shade(cell, zebra)


def add_field(paragraph, instr):
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), instr)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "1"
    run.append(text)
    fld.append(run)
    paragraph._p.append(fld)


def add_header_footer(doc, title):
    section = doc.sections[0]
    if title:
        hp = section.header.paragraphs[0]
        hp.text = title
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    fp = section.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_field(fp, "PAGE")
    fp.add_run(" / ")
    add_field(fp, "NUMPAGES")


def add_table(doc, rows, header, color):
    if not rows:
        return
    cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=cols)
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            table.cell(r, c).text = str(text)
    style_table(table, color, header)
    doc.add_paragraph()  # breathing room after the table


def find_image(path, base):
    for candidate in (Path(base) / path, Path(path)):
        if candidate.is_file():
            return candidate
    sys.exit(f"image not found: {path}")


def save(doc, out):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print(f"saved: {out}")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_create(args):
    content_path = Path(args.content)
    # utf-8-sig also accepts files saved with a BOM (e.g. by Windows Notepad)
    content = json.loads(content_path.read_text(encoding="utf-8-sig"))
    st = resolve_settings(args, content)

    doc = Document()
    apply_styles(doc, st)
    doc.core_properties.title = content.get("title", "")
    doc.core_properties.author = content.get("author", "")
    if not args.no_footer:
        add_header_footer(doc, content.get("title"))
    if content.get("title"):
        doc.add_heading(content["title"], 0)

    for b in content.get("blocks", []):
        t = b.get("type")
        if t == "heading":
            doc.add_heading(b["text"], b.get("level", 1))
        elif t == "paragraph":
            doc.add_paragraph(b["text"])
        elif t == "bullets":
            for item in b["items"]:
                doc.add_paragraph(item, style="List Bullet")
        elif t == "numbered":
            for item in b["items"]:
                doc.add_paragraph(item, style="List Number")
        elif t == "table":
            add_table(doc, b["rows"], b.get("header", True), st["color"])
        elif t == "image":
            img = find_image(b["path"], content_path.parent)
            doc.add_picture(str(img), width=Cm(b.get("width_cm", 14)))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif t == "page_break":
            doc.add_page_break()
        else:
            sys.exit(f"unknown block type: {t!r}")
    save(doc, args.output)


def cmd_read(args):
    doc = Document(args.file)
    for p in doc.paragraphs:
        print(f"[{p.style.name}] {p.text}")
    for i, table in enumerate(doc.tables, 1):
        print(f"--- table {i} ---")
        for row in table.rows:
            print(" | ".join(c.text for c in row.cells))


def iter_paragraphs(doc):
    yield from doc.paragraphs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs


def replace_in_paragraph(p, old, new):
    """Replace within a paragraph. Try per-run first (keeps formatting);
    fall back to merging runs when the text is split across runs."""
    count = 0
    for run in p.runs:
        if old in run.text:
            count += run.text.count(old)
            run.text = run.text.replace(old, new)
    if old in p.text and p.runs:
        count += p.text.count(old)
        p.runs[0].text = p.text.replace(old, new)
        for run in p.runs[1:]:
            run.text = ""
    return count


def cmd_replace(args):
    doc = Document(args.file)
    total = sum(replace_in_paragraph(p, args.old, args.new) for p in iter_paragraphs(doc))
    print(f"replaced {total} occurrence(s)")
    save(doc, args.output or args.file)


def cmd_append(args):
    doc = Document(args.file)
    for text in args.texts:
        doc.add_paragraph(text)
    save(doc, args.output or args.file)


def cmd_restyle(args):
    st = resolve_settings(args)
    doc = Document(args.file)
    apply_styles(doc, st)
    for table in doc.tables:
        style_table(table, st["color"], header=True)
    print(f"restyled: color={st['color']} title={st['title_px']:g}px "
          f"body={st['body_px']:g}px font={st['font']}")
    save(doc, args.output or args.file)


def cmd_colors(_args):
    for name, hex_ in NAMED_COLORS.items():
        label = "ko" if name in KO_LABEL or name in {"빨간", "파란", "녹", "노란", "검은"} else "en"
        print(f"{name:<10} #{hex_}  ({label})")
    print("Any HEX value also works, e.g. #1F4E79, 1F4E79 or #1AF.")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def add_style_args(p):
    p.add_argument("--color", help="main color: name or HEX (default 1F4E79)")
    p.add_argument("--title-px", dest="title_px", type=float,
                   help="title size in px (default 40)")
    p.add_argument("--body-px", dest="body_px", type=float,
                   help="body size in px (default 20)")
    p.add_argument("--font", help="font name (default 맑은 고딕)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create", help="build a .docx from a JSON file")
    p.add_argument("content")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--no-footer", action="store_true",
                   help="omit the header title and the page-number footer")
    add_style_args(p)
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("read", help="print contents of a .docx")
    p.add_argument("file")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("replace", help="find and replace text")
    p.add_argument("file")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("-o", "--output", help="output path (default: overwrite input)")
    p.set_defaults(func=cmd_replace)

    p = sub.add_parser("append", help="append paragraphs")
    p.add_argument("file")
    p.add_argument("texts", nargs="+")
    p.add_argument("-o", "--output", help="output path (default: overwrite input)")
    p.set_defaults(func=cmd_append)

    p = sub.add_parser("restyle", help="re-apply font, sizes and color to a .docx")
    p.add_argument("file")
    p.add_argument("-o", "--output", help="output path (default: overwrite input)")
    add_style_args(p)
    p.set_defaults(func=cmd_restyle)

    p = sub.add_parser("colors", help="list supported color names")
    p.set_defaults(func=cmd_colors)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
