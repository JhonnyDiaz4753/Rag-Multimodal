"""Adaptador de extracción de texto, tablas e imágenes con PyMuPDF."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pymupdf

from src.application.ports.document_parser import DocumentParserPort
from src.application.ports.image_storage import ImageStoragePort
from src.domain.entities import (
    BBox,
    Document,
    ImageRef,
    Page,
    TableBlock,
    TextBlock,
)
from src.infrastructure.images.pymupdf_image_extractor import PymupdfImageExtractor

_BODY_HEADING_RATIO = 1.5
_MAX_HEADING_LEVEL = 6
_BOLD_FLAG = 16


class PymupdfDocumentParser(DocumentParserPort):
    """Extrae bloques de texto y tablas con coordenadas de un PDF."""

    def __init__(self, image_storage: ImageStoragePort | None = None) -> None:
        self._image_extractor = (
            PymupdfImageExtractor(image_storage) if image_storage is not None else None
        )

    def parse(self, pdf_path: Path, *, doc_id: str, filename: str) -> Document:
        images_by_page: dict[int, list[ImageRef]] = {}
        if self._image_extractor is not None:
            for image in self._image_extractor.extract(pdf_path, doc_id=doc_id):
                images_by_page.setdefault(image.page, []).append(image)

        with pymupdf.open(str(pdf_path)) as document:
            blocks_by_page: dict[int, list[TextBlock]] = {}
            tables_by_page: dict[int, list[TableBlock]] = {}
            all_blocks: list[TextBlock] = []

            for page_number, page in enumerate(document, start=1):
                tables = self._extract_tables(page, page_number)
                blocks = self._extract_blocks(
                    page,
                    page_number,
                    table_bboxes=[table.bbox for table in tables],
                )
                blocks_by_page[page_number] = blocks
                tables_by_page[page_number] = tables
                all_blocks.extend(blocks)

            body_size = self._body_size(all_blocks)
            for page_number, blocks in blocks_by_page.items():
                blocks_by_page[page_number] = [
                    replace(block, heading_level=self._heading_level(block, body_size))
                    for block in blocks
                ]

            pages = tuple(
                Page(
                    number=page_number,
                    text_blocks=tuple(blocks_by_page.get(page_number, [])),
                    tables=tuple(tables_by_page.get(page_number, [])),
                    images=tuple(images_by_page.get(page_number, [])),
                )
                for page_number in range(1, document.page_count + 1)
            )

        return Document(doc_id=doc_id, filename=filename, pages=pages)

    def _extract_blocks(
        self,
        page: pymupdf.Page,
        page_number: int,
        *,
        table_bboxes: Sequence[BBox] = (),
    ) -> list[TextBlock]:
        blocks: list[TextBlock] = []

        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [
                    span for span in line.get("spans", []) if str(span.get("text", "")).strip()
                ]
                if not spans:
                    continue
                bbox = line.get("bbox") or block.get("bbox")
                line_bbox = BBox(
                    float(bbox[0]),
                    float(bbox[1]),
                    float(bbox[2]),
                    float(bbox[3]),
                )
                if any(line_bbox.intersects(table_bbox) for table_bbox in table_bboxes):
                    continue
                blocks.append(
                    TextBlock(
                        page=page_number,
                        bbox=line_bbox,
                        text=self._line_text(line),
                        font_size=max(float(span["size"]) for span in spans),
                        is_bold=any(bool(span.get("flags", 0) & _BOLD_FLAG) for span in spans),
                        heading_level=0,
                    )
                )

        return blocks

    def _extract_tables(self, page: pymupdf.Page, page_number: int) -> list[TableBlock]:
        tables: list[TableBlock] = []
        for table in page.find_tables().tables:
            rows = table.extract()
            if not rows:
                continue
            tables.append(
                TableBlock(
                    page=page_number,
                    bbox=BBox(*(float(value) for value in table.bbox)),
                    markdown=self._table_markdown(rows),
                )
            )
        return tables

    @staticmethod
    def _table_markdown(rows: Sequence[Sequence[str | None]]) -> str:
        column_count = max(len(row) for row in rows)
        markdown_rows = [
            "| "
            + " | ".join(
                str(row[index] or "")
                .replace("\r", " ")
                .replace("\n", " ")
                .replace("|", r"\|")
                .strip()
                if index < len(row)
                else ""
                for index in range(column_count)
            )
            + " |"
            for row in rows
        ]
        separator = "| " + " | ".join("---" for _ in range(column_count)) + " |"
        return "\n".join((markdown_rows[0], separator, *markdown_rows[1:]))

    def _line_text(self, line: dict[str, Any]) -> str:
        return "".join(str(span.get("text", "")) for span in line.get("spans", [])).strip()

    @staticmethod
    def _body_size(blocks: Sequence[TextBlock]) -> float:
        if not blocks:
            return 0.0
        return float(statistics.median([block.font_size for block in blocks]))

    def _heading_level(self, block: TextBlock, body_size: float) -> int:
        if body_size <= 0:
            return 0
        if block.font_size < body_size * _BODY_HEADING_RATIO and not block.is_bold:
            return 0
        ratio = block.font_size / body_size
        level = int(math.ceil(math.log(ratio) / math.log(_BODY_HEADING_RATIO)))
        return max(1, min(level, _MAX_HEADING_LEVEL))
