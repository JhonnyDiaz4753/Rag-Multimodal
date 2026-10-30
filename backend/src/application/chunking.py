"""Construcción de chunks a partir del layout estructurado de un documento."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from src.domain.entities import (
    BBox,
    Chunk,
    ChunkKind,
    Document,
    ImageRef,
    Page,
    TableBlock,
    TextBlock,
)

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_FIGURE_CAPTION_PATTERN = re.compile(
    r"\bfigura\s+(?:\d+(?:\.\d+)*|[ivxlcdm]+|[a-z])\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _TextSpan:
    text: str
    bbox: BBox


class LayoutChunker:
    """Genera chunks por sección, con límite y solapamiento de tokens."""

    def __init__(self, *, max_tokens: int = 512, overlap_tokens: int = 32) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens debe ser >= 1")
        if overlap_tokens < 0 or overlap_tokens >= max_tokens:
            raise ValueError("overlap_tokens debe estar entre 0 y max_tokens - 1")
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, document: Document) -> tuple[Chunk, ...]:
        chunks: list[Chunk] = []
        heading_stack: list[tuple[str, BBox]] = []

        for page in document.pages:
            page_items = sorted(
                (*page.text_blocks, *page.tables),
                key=lambda item: (item.bbox.y0, item.bbox.x0),
            )
            section_spans: list[_TextSpan] = []

            for item in page_items:
                if isinstance(item, TextBlock) and item.heading_level > 0:
                    self._flush_section(document, page, section_spans, heading_stack, chunks)
                    heading_stack[:] = heading_stack[: item.heading_level - 1]
                    heading_stack.append((item.text, item.bbox))
                elif isinstance(item, TableBlock):
                    self._flush_section(document, page, section_spans, heading_stack, chunks)
                    chunks.append(
                        self._make_chunk(
                            document,
                            page.number,
                            len(chunks),
                            self._with_heading_path(item.markdown, heading_stack),
                            tuple(bbox for _, bbox in heading_stack) + (item.bbox,),
                            tuple(title for title, _ in heading_stack),
                            kind=ChunkKind.TABLE,
                        )
                    )
                else:
                    section_spans.append(_TextSpan(item.text, item.bbox))

            self._flush_section(document, page, section_spans, heading_stack, chunks)

        return self._attach_images(document, chunks)

    def count_tokens(self, text: str) -> int:
        """Cuenta tokens léxicos (palabras y signos de puntuación)."""
        return sum(1 for _ in _TOKEN_PATTERN.finditer(text))

    def _flush_section(
        self,
        document: Document,
        page: Page,
        spans: list[_TextSpan],
        heading_stack: Sequence[tuple[str, BBox]],
        chunks: list[Chunk],
    ) -> None:
        if not spans:
            return
        chunks.extend(
            self._chunk_section(
                document,
                page,
                spans,
                tuple(title for title, _ in heading_stack),
                tuple(bbox for _, bbox in heading_stack),
                len(chunks),
            )
        )
        spans.clear()

    def _chunk_section(
        self,
        document: Document,
        page: Page,
        spans: Sequence[_TextSpan],
        heading_path: tuple[str, ...],
        heading_bboxes: tuple[BBox, ...],
        first_index: int,
    ) -> list[Chunk]:
        body_parts: list[str] = []
        body_spans: list[tuple[int, int, BBox]] = []
        cursor = 0
        for span in spans:
            if body_parts:
                body_parts.append("\n")
                cursor += 1
            start = cursor
            body_parts.append(span.text)
            cursor += len(span.text)
            body_spans.append((start, cursor, span.bbox))

        body = "".join(body_parts)
        tokens = list(_TOKEN_PATTERN.finditer(body))
        if not tokens:
            return []

        prefix = self._heading_prefix(heading_path)
        prefix_tokens = self.count_tokens(prefix)
        if prefix_tokens >= self.max_tokens:
            raise ValueError(
                "el heading_path ocupa el límite completo de tokens configurado para un chunk"
            )
        token_capacity = self.max_tokens - prefix_tokens
        overlap = min(self.overlap_tokens, token_capacity - 1)

        chunks: list[Chunk] = []
        token_start = 0
        while token_start < len(tokens):
            token_end = min(token_start + token_capacity, len(tokens))
            char_start = tokens[token_start].start()
            char_end = tokens[token_end - 1].end()
            chunk_body = body[char_start:char_end]
            chunk_bboxes = [
                bbox
                for span_start, span_end, bbox in body_spans
                if span_start < char_end and char_start < span_end
            ]
            chunks.append(
                self._make_chunk(
                    document,
                    page.number,
                    first_index + len(chunks),
                    self._with_heading_path(chunk_body, heading_path),
                    (*heading_bboxes, *chunk_bboxes),
                    heading_path,
                    kind=ChunkKind.TEXT,
                )
            )
            if token_end == len(tokens):
                break
            token_start = token_end - overlap

        return chunks

    @staticmethod
    def _heading_prefix(heading_path: Sequence[str]) -> str:
        return " > ".join(heading_path)

    @classmethod
    def _with_heading_path(cls, text: str, heading_path: Sequence[str]) -> str:
        prefix = cls._heading_prefix(heading_path)
        return f"{prefix}\n\n{text}" if prefix else text

    @staticmethod
    def _make_chunk(
        document: Document,
        page: int,
        index: int,
        text: str,
        bboxes: Sequence[BBox],
        heading_path: tuple[str, ...],
        *,
        kind: ChunkKind,
        image_ids: tuple[str, ...] = (),
    ) -> Chunk:
        return Chunk(
            id=f"{document.doc_id}:{index}",
            doc_id=document.doc_id,
            filename=document.filename,
            text=text,
            page=page,
            bboxes=tuple(dict.fromkeys(bboxes)),
            heading_path=heading_path,
            image_ids=image_ids,
            kind=kind,
        )

    def _attach_images(self, document: Document, chunks: list[Chunk]) -> tuple[Chunk, ...]:
        for page in document.pages:
            page_candidates = [
                (
                    index,
                    chunks[index].bboxes,
                    bool(_FIGURE_CAPTION_PATTERN.search(chunks[index].text)),
                )
                for index in range(len(chunks))
                if chunks[index].page == page.number
            ]
            for image in page.images:
                if not page_candidates:
                    chunks.append(self._image_chunk(document, image, len(chunks)))
                    continue
                caption_candidates = [candidate for candidate in page_candidates if candidate[2]]
                candidates = caption_candidates or page_candidates
                target_index, _, _ = min(
                    candidates,
                    key=lambda candidate: self._image_distance(image.bbox, candidate[1]),
                )
                target = chunks[target_index]
                chunks[target_index] = replace(
                    target,
                    bboxes=tuple(dict.fromkeys((*target.bboxes, image.bbox))),
                    image_ids=(*target.image_ids, image.id),
                )
        return tuple(chunks)

    @staticmethod
    def _image_distance(image_bbox: BBox, chunk_bboxes: Sequence[BBox]) -> float:
        if not chunk_bboxes:
            return float("inf")
        return min(image_bbox.vertical_distance(bbox) for bbox in chunk_bboxes)

    @staticmethod
    def _image_chunk(document: Document, image: ImageRef, index: int) -> Chunk:
        return Chunk(
            id=f"{document.doc_id}:{index}",
            doc_id=document.doc_id,
            filename=document.filename,
            text=image.caption or f"Imagen {image.id}",
            page=image.page,
            bboxes=(image.bbox,),
            image_ids=(image.id,),
            kind=ChunkKind.IMAGE,
        )
