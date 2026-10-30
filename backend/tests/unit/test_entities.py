"""Tests de las entidades y reglas de negocio del dominio."""

from __future__ import annotations

from datetime import UTC

import pytest

from src.domain import (
    Answer,
    BBox,
    Chunk,
    ChunkKind,
    Document,
    ImageRef,
    Job,
    JobStatus,
    Page,
    RetrievedChunk,
    Source,
    TableBlock,
    TextBlock,
)
from src.domain.errors import DomainValidationError, InvalidJobTransitionError


def _bbox(x0: float = 0.0, y0: float = 0.0, x1: float = 10.0, y1: float = 10.0) -> BBox:
    return BBox(x0, y0, x1, y1)


def _make_chunk(chunk_id: str = "c1", text: str = "contenido", page: int = 1) -> Chunk:
    return Chunk(id=chunk_id, doc_id="d1", filename="manual.pdf", text=text, page=page)


def test_bbox_dimensions_and_area() -> None:
    box = _bbox(10, 20, 40, 50)

    assert box.width == 30
    assert box.height == 30
    assert box.area == 900


def test_bbox_allows_zero_area() -> None:
    box = _bbox(5, 5, 5, 5)

    assert box.area == 0


@pytest.mark.parametrize(
    "coords",
    [
        (10, 0, 0, 10),
        (0, 10, 10, 0),
    ],
)
def test_bbox_rejects_inverted_coordinates(coords: tuple[float, float, float, float]) -> None:
    with pytest.raises(DomainValidationError, match="BBox inválido"):
        BBox(*coords)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_bbox_rejects_non_finite_coordinates(value: float) -> None:
    with pytest.raises(DomainValidationError, match="finitas"):
        BBox(0, 0, value, 10)


def test_bbox_vertical_distance_with_gap() -> None:
    top, bottom = _bbox(0, 0, 10, 10), _bbox(0, 25, 10, 40)

    assert top.vertical_distance(bottom) == 15
    assert bottom.vertical_distance(top) == 15


def test_bbox_vertical_distance_overlap_and_touching_is_zero() -> None:
    assert _bbox(0, 0, 10, 20).vertical_distance(_bbox(0, 10, 10, 30)) == 0
    assert _bbox(0, 0, 10, 10).vertical_distance(_bbox(0, 10, 10, 20)) == 0


def test_bbox_horizontal_distance_with_gap_and_overlap() -> None:
    left, right = _bbox(0, 0, 10, 10), _bbox(25, 0, 40, 10)

    assert left.horizontal_distance(right) == 15
    assert right.horizontal_distance(left) == 15
    assert _bbox(0, 0, 20, 10).horizontal_distance(_bbox(10, 0, 30, 10)) == 0


def test_bbox_intersects_only_with_positive_overlap() -> None:
    box = _bbox(0, 0, 10, 10)

    assert box.intersects(_bbox(5, 5, 15, 15)) is True
    assert box.intersects(_bbox(10, 0, 20, 10)) is False
    assert box.intersects(_bbox(20, 20, 30, 30)) is False


def test_bbox_union_contains_both_boxes() -> None:
    union = _bbox(0, 0, 10, 10).union(_bbox(20, 5, 30, 15))

    assert union == BBox(0, 0, 30, 15)


def test_chunk_defaults() -> None:
    chunk = _make_chunk()

    assert chunk.kind is ChunkKind.TEXT
    assert chunk.bboxes == ()
    assert chunk.heading_path == ()
    assert chunk.image_ids == ()


def test_chunk_rejects_empty_text() -> None:
    with pytest.raises(DomainValidationError, match="text"):
        _make_chunk(text="   ")


def test_chunk_rejects_invalid_page() -> None:
    with pytest.raises(DomainValidationError, match="página"):
        _make_chunk(page=0)


def test_chunk_kind_serializes_as_string() -> None:
    assert ChunkKind.TABLE == "table"


def test_image_ref_defaults() -> None:
    image = ImageRef(id="i1", doc_id="d1", page=2, bbox=_bbox(), path="images/i1.png")

    assert image.caption is None


def test_image_ref_requires_path_and_valid_page() -> None:
    with pytest.raises(DomainValidationError, match="path"):
        ImageRef(id="i1", doc_id="d1", page=1, bbox=_bbox(), path=" ")
    with pytest.raises(DomainValidationError, match="página"):
        ImageRef(id="i1", doc_id="d1", page=0, bbox=_bbox(), path="i1.png")


def test_text_block_requires_positive_font_size() -> None:
    with pytest.raises(DomainValidationError, match="font_size"):
        TextBlock(page=1, bbox=_bbox(), text="hola", font_size=0)


def test_table_block_requires_markdown() -> None:
    with pytest.raises(DomainValidationError, match="markdown"):
        TableBlock(page=1, bbox=_bbox(), markdown="")


def test_page_rejects_blocks_from_other_pages() -> None:
    block = TextBlock(page=2, bbox=_bbox(), text="hola", font_size=10)

    with pytest.raises(DomainValidationError, match="no pertenece"):
        Page(number=1, text_blocks=(block,))


def test_document_exposes_its_pages() -> None:
    document = Document(
        doc_id="d1",
        filename="manual.pdf",
        pages=(Page(number=1), Page(number=2)),
    )

    page = document.page(2)
    assert document.page_count == 2
    assert page is not None
    assert page.number == 2
    assert document.page(3) is None


def test_document_rejects_duplicate_pages() -> None:
    with pytest.raises(DomainValidationError, match="repetirse"):
        Document(doc_id="d1", filename="manual.pdf", pages=(Page(number=1), Page(number=1)))


def test_document_requires_filename() -> None:
    with pytest.raises(DomainValidationError, match="filename"):
        Document(doc_id="d1", filename="")


def test_job_defaults() -> None:
    job = Job(id="j1", doc_id="d1")

    assert job.status is JobStatus.PENDING
    assert job.stage == "queued"
    assert job.progress == 0
    assert job.error is None
    assert job.created_at.tzinfo == UTC
    assert job.updated_at >= job.created_at


def test_job_start_moves_to_processing() -> None:
    job = Job(id="j1", doc_id="d1")

    job.start(stage="parsing")

    assert job.status is JobStatus.PROCESSING
    assert job.stage == "parsing"
    assert job.error is None
    assert job.updated_at >= job.created_at


def test_job_cannot_start_twice() -> None:
    job = Job(id="j1", doc_id="d1")
    job.start()

    with pytest.raises(InvalidJobTransitionError, match="iniciar"):
        job.start()


def test_job_advance_updates_progress_and_stage() -> None:
    job = Job(id="j1", doc_id="d1")
    job.start()

    job.advance(40, stage="chunking")

    assert job.progress == 40
    assert job.stage == "chunking"


def test_job_advance_allows_same_progress_but_not_regression() -> None:
    job = Job(id="j1", doc_id="d1")
    job.start()
    job.advance(40)

    job.advance(40)

    with pytest.raises(InvalidJobTransitionError, match="retroceder"):
        job.advance(39)


@pytest.mark.parametrize("progress", [-1, 101])
def test_job_advance_rejects_out_of_range_progress(progress: int) -> None:
    job = Job(id="j1", doc_id="d1")
    job.start()

    with pytest.raises(DomainValidationError, match="entre 0 y 100"):
        job.advance(progress)


def test_job_advance_requires_processing_state() -> None:
    with pytest.raises(InvalidJobTransitionError, match="avanzar"):
        Job(id="j1", doc_id="d1").advance(10)


def test_job_complete_sets_final_state() -> None:
    job = Job(id="j1", doc_id="d1")
    job.start()
    job.advance(80)

    job.complete()

    assert job.status is JobStatus.COMPLETED
    assert job.stage == "completed"
    assert job.progress == 100
    assert job.error is None


def test_job_complete_requires_processing_state() -> None:
    with pytest.raises(InvalidJobTransitionError, match="completar"):
        Job(id="j1", doc_id="d1").complete()


def test_job_fail_from_pending() -> None:
    job = Job(id="j1", doc_id="d1")

    job.fail("PDF corrupto")

    assert job.status is JobStatus.FAILED
    assert job.stage == "failed"
    assert job.error == "PDF corrupto"


def test_job_fail_requires_error_message() -> None:
    with pytest.raises(DomainValidationError, match="error"):
        Job(id="j1", doc_id="d1").fail("   ")


@pytest.mark.parametrize("terminal", ["complete", "fail"])
def test_job_cannot_leave_terminal_state(terminal: str) -> None:
    job = Job(id="j1", doc_id="d1")
    job.start()
    if terminal == "complete":
        job.complete()
    else:
        job.fail("boom")

    with pytest.raises(InvalidJobTransitionError, match="ya está en estado"):
        job.fail("otra vez")


def test_job_rejects_invalid_initial_progress() -> None:
    with pytest.raises(DomainValidationError, match="entre 0 y 100"):
        Job(id="j1", doc_id="d1", progress=120)


def test_job_rejects_blank_stage() -> None:
    with pytest.raises(DomainValidationError, match="stage"):
        Job(id="j1", doc_id="d1", stage=" ")


def test_answer_with_sources_is_valid() -> None:
    source = Source(filename="manual.pdf", page=3, chunk_id="c1")

    answer = Answer(text="La respuesta es 42.", sufficient_info=True, sources=(source,))

    assert answer.sources == (source,)
    assert answer.image is None


def test_answer_requires_sources_when_info_is_sufficient() -> None:
    with pytest.raises(DomainValidationError, match="fuente"):
        Answer(text="La respuesta es 42.", sufficient_info=True)


def test_answer_allows_insufficient_info_without_sources() -> None:
    answer = Answer(text="No encuentro esa información.", sufficient_info=False)

    assert answer.sources == ()


def test_answer_requires_text() -> None:
    with pytest.raises(DomainValidationError, match="text"):
        Answer(text="", sufficient_info=False)


def test_source_requires_valid_page() -> None:
    with pytest.raises(DomainValidationError, match="página"):
        Source(filename="manual.pdf", page=0, chunk_id="c1")


def test_retrieved_chunk_rejects_non_finite_score() -> None:
    with pytest.raises(DomainValidationError, match="finito"):
        RetrievedChunk(chunk=_make_chunk(), score=float("nan"))


def test_retrieved_chunk_keeps_chunk_and_score() -> None:
    chunk = _make_chunk()

    retrieved = RetrievedChunk(chunk=chunk, score=0.75)

    assert retrieved.chunk is chunk
    assert retrieved.score == 0.75
