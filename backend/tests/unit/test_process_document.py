from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from src.application.chunking import LayoutChunker
from src.application.process_document import ProcessDocumentUseCase
from src.domain import BBox, Document, Page, TextBlock
from src.domain.jod import Job, JobStatus


class _Jobs:
    def __init__(self, job: Job) -> None:
        self.job = job
        self.saved: list[Job] = []

    async def get(self, job_id: str) -> Job | None:
        return self.job if job_id == self.job.id else None

    async def save(self, job: Job) -> None:
        self.saved.append(replace(job))


class _Parser:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.arguments: tuple[Path, str, str] | None = None

    def parse(self, pdf_path: Path, *, doc_id: str, filename: str) -> Document:
        self.arguments = (pdf_path, doc_id, filename)
        if self.error:
            raise self.error
        return Document(
            doc_id=doc_id,
            filename=filename,
            pages=(
                Page(
                    number=1,
                    text_blocks=(
                        TextBlock(
                            page=1,
                            bbox=BBox(0, 0, 100, 10),
                            text="Contenido del manual.",
                            font_size=12,
                        ),
                    ),
                ),
            ),
        )


class _Embeddings:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.texts: Sequence[str] = ()

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.texts = texts
        if self.error:
            raise self.error
        return [[0.1, 0.2] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class _VectorStore:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.collection_created = False
        self.upserted: tuple[Sequence[object], Sequence[Sequence[float]]] | None = None

    async def ensure_collection(self) -> None:
        self.collection_created = True

    async def upsert(self, chunks: Sequence[object], vectors: Sequence[Sequence[float]]) -> None:
        if self.error:
            raise self.error
        self.upserted = (chunks, vectors)

    async def hybrid_search(self, **kwargs: object) -> list[object]:
        raise NotImplementedError

    async def delete_document(self, doc_id: str) -> None:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_pipeline_updates_progress_for_each_stage_and_completes() -> None:
    job = Job(id="job-1", document_id="doc-1", filename="manual.pdf")
    jobs = _Jobs(job)
    parser = _Parser()
    embeddings = _Embeddings()
    vector_store = _VectorStore()
    use_case = ProcessDocumentUseCase(
        jobs=jobs,
        parser=parser,
        chunker=LayoutChunker(),
        embeddings=embeddings,
        vector_store=vector_store,
    )

    await use_case.execute("job-1", "doc-1", "uploads/manual.pdf")

    assert [(saved.stage, saved.progress) for saved in jobs.saved] == [
        ("parsing", 0),
        ("chunking", 25),
        ("embedding", 50),
        ("indexing", 75),
        ("completed", 100),
    ]
    assert jobs.saved[-1].status is JobStatus.COMPLETED
    assert jobs.saved[-1].error is None
    assert parser.arguments == (Path("uploads/manual.pdf"), "doc-1", "manual.pdf")
    assert embeddings.texts == ["Contenido del manual."]
    assert vector_store.collection_created
    assert vector_store.upserted is not None
    assert len(vector_store.upserted[0]) == len(vector_store.upserted[1]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("parser_error", "embedding_error", "indexing_error", "failed_stage", "error_reason"),
    [
        (RuntimeError("PDF ilegible"), None, None, "parsing", "PDF ilegible"),
        (
            None,
            RuntimeError("Proveedor no disponible"),
            None,
            "embedding",
            "Proveedor no disponible",
        ),
        (
            None,
            None,
            RuntimeError("Qdrant no disponible"),
            "indexing",
            "Qdrant no disponible",
        ),
    ],
)
async def test_pipeline_persists_failed_status_and_reason(
    parser_error: Exception | None,
    embedding_error: Exception | None,
    indexing_error: Exception | None,
    failed_stage: str,
    error_reason: str,
) -> None:
    job = Job(id="job-1", document_id="doc-1", filename="manual.pdf")
    jobs = _Jobs(job)
    use_case = ProcessDocumentUseCase(
        jobs=jobs,
        parser=_Parser(parser_error),
        chunker=LayoutChunker(),
        embeddings=_Embeddings(embedding_error),
        vector_store=_VectorStore(indexing_error),
    )

    with pytest.raises(RuntimeError):
        await use_case.execute("job-1", "doc-1", "uploads/manual.pdf")

    failed = jobs.saved[-1]
    assert failed.status is JobStatus.FAILED
    assert failed.stage == failed_stage
    assert failed.progress < 100
    assert failed.error is not None
    assert failed.error.startswith("RuntimeError:")
    assert failed.error == f"RuntimeError: {error_reason}"


@pytest.mark.asyncio
async def test_pipeline_rejects_job_document_mismatch() -> None:
    job = Job(id="job-1", document_id="doc-1", filename="manual.pdf")
    jobs = _Jobs(job)
    use_case = ProcessDocumentUseCase(
        jobs=jobs,
        parser=_Parser(),
        chunker=LayoutChunker(),
        embeddings=_Embeddings(),
        vector_store=_VectorStore(),
    )

    with pytest.raises(ValueError, match="no coincide"):
        await use_case.execute("job-1", "other-doc", "uploads/manual.pdf")

    assert jobs.saved == []
