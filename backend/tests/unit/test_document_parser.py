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
