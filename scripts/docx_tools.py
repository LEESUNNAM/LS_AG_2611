"""Command-line helpers for Word documents, built on python-docx.

Commands:
  create   Build a new .docx from a JSON content file.
  read     Print paragraphs (with style) and tables of a .docx.
  replace  Find and replace text, keeping run formatting where possible.
  append   Append paragraphs to the end of an existing .docx.

Examples:
  python scripts/docx_tools.py create scripts/examples/sample_content.json -o output/doc.docx
  python scripts/docx_tools.py read output/doc.docx
  python scripts/docx_tools.py replace output/doc.docx "old" "new" -o output/doc2.docx
  python scripts/docx_tools.py append output/doc.docx "More text" "Another" -o output/doc3.docx

JSON content format (blocks are written in order):
  {
    "title": "Document title",
    "blocks": [
      {"type": "heading", "text": "Section", "level": 1},
      {"type": "paragraph", "text": "Body text"},
      {"type": "bullets", "items": ["a", "b"]},
      {"type": "numbered", "items": ["first", "second"]},
      {"type": "table", "rows": [["h1", "h2"], ["c1", "c2"]], "header": true},
      {"type": "page_break"}
    ]
  }
"""
import argparse
import json
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

FONT = "맑은 고딕"
STYLES_TO_FONT = ("Normal", "Title", "Heading 1", "Heading 2", "Heading 3",
                  "List Bullet", "List Number")


def apply_font(doc, name=FONT, size=11):
    for s in STYLES_TO_FONT:
        style = doc.styles[s]
        style.font.name = name
        style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), name)
    doc.styles["Normal"].font.size = Pt(size)


def add_table(doc, rows, header=True):
    if not rows:
        return
    cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=cols)
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            cell = table.cell(r, c)
            cell.text = str(text)
            if header and r == 0:
                for run in cell.paragraphs[0].runs:
                    run.bold = True


def save(doc, out):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print(f"saved: {out}")


def cmd_create(args):
    content = json.loads(Path(args.content).read_text(encoding="utf-8"))
    doc = Document()
    apply_font(doc)
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
            add_table(doc, b["rows"], b.get("header", True))
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
        merged = p.text.replace(old, new)
        p.runs[0].text = merged
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create", help="build a .docx from a JSON file")
    p.add_argument("content")
    p.add_argument("-o", "--output", required=True)
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

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
