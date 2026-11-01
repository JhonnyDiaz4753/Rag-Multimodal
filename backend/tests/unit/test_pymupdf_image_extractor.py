"""Tests del adaptador de extracción de imágenes con PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from src.domain import BBox
from src.infrastructure.images import LocalImageStorage, PymupdfImageExtractor
from src.infrastructure.parsers import PymupdfDocumentParser


def _write_pdf_with_image(path: Path, *, size: int) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, size, size))
    page.insert_image(pymupdf.Rect(50, 200, 200, 300), pixmap=pixmap)
    document.save(str(path))
    document.close()
    return path


def test_extractor_saves_relevant_images(tmp_path: Path) -> None:
    storage = LocalImageStorage(tmp_path)
    extractor = PymupdfImageExtractor(storage)
    refs = extractor.extract(_write_pdf_with_image(tmp_path / "sample.pdf", size=64), doc_id="d1")

    assert len(refs) == 1
    ref = refs[0]
    assert ref.doc_id == "d1"
    assert ref.page == 1
    assert ref.caption is None
    assert ref.bbox == BBox(50.0, 200.0, 200.0, 300.0)
    assert storage.read(ref.id) is not None


def test_extractor_discards_images_below_threshold(tmp_path: Path) -> None:
    storage = LocalImageStorage(tmp_path)
    extractor = PymupdfImageExtractor(storage)
    refs = extractor.extract(_write_pdf_with_image(tmp_path / "small.pdf", size=8), doc_id="d1")

    assert refs == ()


def test_document_parser_includes_extracted_images(tmp_path: Path) -> None:
    storage = LocalImageStorage(tmp_path)
    parser = PymupdfDocumentParser(storage)

    document = parser.parse(
        _write_pdf_with_image(tmp_path / "sample.pdf", size=64),
        doc_id="d1",
        filename="sample.pdf",
    )

    assert len(document.pages[0].images) == 1
    assert storage.get(document.pages[0].images[0].id) == document.pages[0].images[0]
