from __future__ import annotations

import pytest

from src.application.chunking import LayoutChunker
from src.domain import BBox, ChunkKind, Document, ImageRef, Page, TableBlock, TextBlock


def _text(
    text: str,
    y: float,
    *,
    heading_level: int = 0,
    page: int = 1,
) -> TextBlock:
    return TextBlock(
        page=page,
        bbox=BBox(0, y, 100, y + 10),
        text=text,
        font_size=12,
        heading_level=heading_level,
    )


def _document(*pages: Page) -> Document:
    return Document(doc_id="doc-1", filename="manual.pdf", pages=tuple(pages))


def test_chunks_are_grouped_by_section_and_subsection() -> None:
    document = _document(
        Page(
            number=1,
            text_blocks=(
                _text("Primera sección", 0, heading_level=1),
                _text("Contenido uno.", 20),
                _text("Subsección", 40, heading_level=2),
                _text("Contenido dos.", 60),
                _text("Segunda sección", 80, heading_level=1),
                _text("Contenido tres.", 100),
            ),
        )
    )

    chunks = LayoutChunker().chunk(document)

    assert [chunk.heading_path for chunk in chunks] == [
        ("Primera sección",),
        ("Primera sección", "Subsección"),
        ("Segunda sección",),
    ]
    assert [chunk.text.split("\n\n")[-1] for chunk in chunks] == [
        "Contenido uno.",
        "Contenido dos.",
        "Contenido tres.",
    ]
    assert all(chunk.heading_path[0] in chunk.text for chunk in chunks)


def test_long_section_respects_token_limit_and_overlaps_minimally() -> None:
    body = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar"
    document = _document(
        Page(
            number=1,
            text_blocks=(
                _text("Capitulo", 0, heading_level=1),
                _text(body, 20),
            ),
        )
    )
    chunker = LayoutChunker(max_tokens=8, overlap_tokens=2)

    chunks = chunker.chunk(document)

    assert len(chunks) == 3
    assert all(chunker.count_tokens(chunk.text) <= 8 for chunk in chunks)
    bodies = [chunk.text.split("\n\n")[-1].split() for chunk in chunks]
    assert bodies[0][-2:] == bodies[1][:2]
    assert bodies[1][-2:] == bodies[2][:2]
    assert body.split() == [
        *bodies[0],
        *bodies[1][2:],
        *bodies[2][2:],
    ]


def test_tables_are_atomic_and_payload_keeps_layout_and_images() -> None:
    image = ImageRef(
        id="image-1",
        doc_id="doc-1",
        page=1,
        bbox=BBox(20, 20, 30, 30),
        path="image.png",
    )
    table = TableBlock(
        page=1,
        bbox=BBox(10, 10, 40, 40),
        markdown="| " + " | ".join(f"value-{index}" for index in range(12)) + " |",
    )
    document = _document(Page(number=1, tables=(table,), images=(image,)))
    chunker = LayoutChunker(max_tokens=3, overlap_tokens=0)

    chunks = chunker.chunk(document)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.kind is ChunkKind.TABLE
    assert chunk.text.endswith(table.markdown)
    assert chunk.bboxes == (table.bbox, image.bbox)
    assert chunk.image_ids == ("image-1",)
    assert chunker.count_tokens(chunk.text) > chunker.max_tokens
    assert chunk.payload == {
        "doc_id": "doc-1",
        "page": 1,
        "bboxes": [[10, 10, 40, 40], [20, 20, 30, 30]],
        "heading_path": [],
        "image_ids": ["image-1"],
    }


def test_image_only_page_produces_valid_image_chunk() -> None:
    image = ImageRef(
        id="image-1",
        doc_id="doc-1",
        page=1,
        bbox=BBox(10, 10, 40, 40),
        path="image.png",
        caption="Diagrama del sistema",
    )
    chunks = LayoutChunker().chunk(_document(Page(number=1, images=(image,))))

    assert len(chunks) == 1
    assert chunks[0].kind is ChunkKind.IMAGE
    assert chunks[0].filename == "manual.pdf"
    assert chunks[0].text == "Diagrama del sistema"
    assert chunks[0].image_ids == ("image-1",)


def test_image_is_associated_by_vertical_distance_not_horizontal_distance() -> None:
    image = ImageRef(
        id="image-1",
        doc_id="doc-1",
        page=1,
        bbox=BBox(200, 100, 240, 120),
        path="image.png",
    )
    document = _document(
        Page(
            number=1,
            text_blocks=(
                _text("Sección cercana", 125, heading_level=1),
                _text("Texto cercano.", 140),
                TextBlock(
                    page=1,
                    bbox=BBox(200, 250, 300, 260),
                    text="Sección lejana",
                    font_size=16,
                    heading_level=1,
                ),
                TextBlock(
                    page=1,
                    bbox=BBox(200, 270, 300, 280),
                    text="Texto lejano.",
                    font_size=12,
                ),
            ),
            images=(image,),
        )
    )

    chunks = LayoutChunker().chunk(document)

    assert len(chunks) == 2
    assert chunks[0].image_ids == ("image-1",)
    assert chunks[1].image_ids == ()


def test_figure_caption_chunk_is_preferred_over_nearer_chunk() -> None:
    image = ImageRef(
        id="image-1",
        doc_id="doc-1",
        page=1,
        bbox=BBox(0, 100, 40, 120),
        path="image.png",
    )
    document = _document(
        Page(
            number=1,
            text_blocks=(
                _text("Sección cercana", 125, heading_level=1),
                _text("Texto cercano.", 140),
                _text("Sección con figura", 250, heading_level=1),
                _text("Figura 1. Diagrama del sistema.", 270),
            ),
            images=(image,),
        )
    )

    chunks = LayoutChunker().chunk(document)

    assert len(chunks) == 2
    assert chunks[0].image_ids == ()
    assert chunks[1].image_ids == ("image-1",)


def test_image_is_not_associated_with_chunks_from_other_pages() -> None:
    image = ImageRef(
        id="image-1",
        doc_id="doc-1",
        page=2,
        bbox=BBox(0, 10, 40, 30),
        path="image.png",
    )
    document = _document(
        Page(number=1, text_blocks=(_text("Otra página", 10, page=1),)),
        Page(number=2, images=(image,)),
    )

    chunks = LayoutChunker().chunk(document)

    assert [chunk.page for chunk in chunks] == [1, 2]
    assert chunks[0].image_ids == ()
    assert chunks[1].image_ids == ("image-1",)
    assert chunks[1].kind is ChunkKind.IMAGE


@pytest.mark.parametrize(
    ("max_tokens", "overlap_tokens"),
    [(0, 0), (10, -1), (10, 10)],
)
def test_chunker_rejects_invalid_token_limits(max_tokens: int, overlap_tokens: int) -> None:
    with pytest.raises(ValueError):
        LayoutChunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
