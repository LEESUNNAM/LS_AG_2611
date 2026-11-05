"""Create a sample Word document with python-docx."""
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

FONT = "맑은 고딕"


def set_font(style, name=FONT, size=None):
    style.font.name = name
    style.element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size:
        style.font.size = Pt(size)


def main():
    doc = Document()
    for s in ("Normal", "Title", "Heading 1", "List Bullet"):
        set_font(doc.styles[s])
    doc.styles["Normal"].font.size = Pt(11)

    doc.add_heading("python-docx 샘플 문서", 0)

    doc.add_heading("소개", 1)
    doc.add_paragraph(
        "이 문서는 python-docx 라이브러리로 자동 생성한 샘플입니다. "
        "제목, 문단, 글머리표 목록, 표를 파이썬 코드만으로 만들 수 있습니다."
    )

    doc.add_heading("주요 기능", 1)
    for item in ("문서 새로 만들기", "문단과 제목 추가", "표와 목록 추가", "기존 문서 수정"):
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("기능 요약표", 1)
    rows = [
        ("기능", "메서드", "설명"),
        ("제목", "add_heading()", "제목과 소제목 추가"),
        ("문단", "add_paragraph()", "본문 문단 추가"),
    ]
    table = doc.add_table(rows=len(rows), cols=3)
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            cell = table.cell(r, c)
            cell.text = text
            if r == 0:
                for run in cell.paragraphs[0].runs:
                    run.bold = True

    doc.add_heading("맺음말", 1)
    doc.add_paragraph("python-docx로 Word 문서 작성을 자동화할 수 있습니다.")

    out = Path(__file__).resolve().parent.parent / "output" / "sample.docx"
    out.parent.mkdir(exist_ok=True)
    doc.save(out)
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
