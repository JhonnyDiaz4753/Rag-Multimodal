"""Tests del adaptador de extracción de documento con PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from src.application.ports import DocumentParserPort
from src.domain import BBox, Document
from src.infrastructure.parsers import PymupdfDocumentParser


def _write_pdf(path: Path, *, headings: bool) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((50, 80), "Parrafo de cuerpo.", fontsize=11, fontname="helv")
    if headings:
        page.insert_text((50, 120), "Capitulo Uno", fontsize=22, fontname="hebo")
        page.insert_text((50, 160), "Seccion A", fontsize=15, fontname="hebo")
    document.save(str(path))
    document.close()
    return path


def _write_pdf_with_table(path: Path) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((50, 80), "Texto anterior.")

    for x in (50, 200, 350):
        page.draw_line((x, 100), (x, 160))
    for y in (100, 130, 160):
        page.draw_line((50, y), (350, y))
    page.insert_text((60, 118), "Parametro")
    page.insert_text((210, 118), "Valor")
    page.insert_text((60, 148), "Presion | max")
    page.insert_text((210, 148), "12 bar")
    page.insert_text((50, 190), "Texto posterior.")

    document.save(str(path))
    document.close()
    return path


def test_parser_implements_document_parser_port() -> None:
    assert isinstance(PymupdfDocumentParser(), DocumentParserPort)


def test_parse_extracts_blocks_with_bboxes_and_headings(tmp_path: Path) -> None:
    parser = PymupdfDocumentParser()
    document = parser.parse(
        _write_pdf(tmp_path / "sample.pdf", headings=True), doc_id="d1", filename="sample.pdf"
    )

    assert isinstance(document, Document)
    assert document.doc_id == "d1"
    assert document.filename == "sample.pdf"
    assert document.page_count == 1

    page = document.pages[0]
    assert page.number == 1

    blocks = page.text_blocks
    by_text = {block.text: block for block in blocks}
    assert set(by_text) == {"Parrafo de cuerpo.", "Capitulo Uno", "Seccion A"}

    for block in blocks:
        assert isinstance(block.bbox, BBox)
        assert block.bbox.area > 0

    assert by_text["Capitulo Uno"].heading_level > 0
    assert by_text["Seccion A"].heading_level > 0
    assert by_text["Parrafo de cuerpo."].heading_level == 0


def test_parse_falls_back_to_paragraphs_without_headings(tmp_path: Path) -> None:
    parser = PymupdfDocumentParser()
    document = parser.parse(
        _write_pdf(tmp_path / "sample.pdf", headings=False), doc_id="d1", filename="sample.pdf"
    )

    blocks = document.pages[0].text_blocks

    assert len(blocks) == 1
    assert blocks[0].text == "Parrafo de cuerpo."
    assert blocks[0].heading_level == 0


def test_parse_extracts_tables_as_markdown_with_bbox(tmp_path: Path) -> None:
    document = PymupdfDocumentParser().parse(
        _write_pdf_with_table(tmp_path / "table.pdf"),
        doc_id="d1",
        filename="table.pdf",
    )

    page = document.pages[0]

    assert len(page.tables) == 1
    table = page.tables[0]
    assert table.page == 1
    assert table.bbox == BBox(50, 100, 350, 160)
    assert table.markdown == ("| Parametro | Valor |\n| --- | --- |\n| Presion \\| max | 12 bar |")
    assert [block.text for block in page.text_blocks] == ["Texto anterior.", "Texto posterior."]
