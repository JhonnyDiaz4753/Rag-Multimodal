from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from src.application.answer_question import AnswerQuestionUseCase
from src.domain import BBox, Chunk, ImageRef, RetrievedChunk


class _Embeddings:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1, 0.2]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class _VectorStore:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.calls: list[dict[str, object]] = []

    async def hybrid_search(self, **kwargs: object) -> list[RetrievedChunk]:
        self.calls.append(kwargs)
        return self.chunks

    async def ensure_collection(self) -> None:
        raise NotImplementedError

    async def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        raise NotImplementedError

    async def delete_document(self, doc_id: str) -> None:
        raise NotImplementedError


class _LLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def generate(self, prompt: str, **kwargs: object) -> str:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.response

    async def describe_image(
        self,
        image: bytes,
        *,
        prompt: str,
        mime_type: str = "image/png",
    ) -> str:
        raise NotImplementedError


class _ImageStorage:
    def __init__(self, images: list[ImageRef]) -> None:
        self.images = {image.id: image for image in images}

    def get(self, image_id: str) -> ImageRef | None:
        return self.images.get(image_id)

    def read(self, image_id: str) -> bytes:
        raise NotImplementedError

    def save(self, **kwargs: object) -> ImageRef:
        raise NotImplementedError


def _retrieved(chunk_id: str, *, score: float, filename: str = "manual.pdf") -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(
            id=chunk_id,
            doc_id="doc-1",
            filename=filename,
            text="La presión nominal es 10 bar.",
            page=2,
            bboxes=(BBox(1, 2, 3, 4),),
        ),
        score=score,
    )


@pytest.mark.asyncio
async def test_query_returns_structured_answer_with_only_retrieved_citations() -> None:
    vector_store = _VectorStore([_retrieved("chunk-1", score=0.8)])
    llm = _LLM(
        json.dumps(
            {
                "answer": "La presión nominal es 10 bar.",
                "sufficient_info": True,
                "sources": [{"chunk_id": "chunk-1"}, {"chunk_id": "invented-chunk"}],
            }
        )
    )
    use_case = AnswerQuestionUseCase(
        _Embeddings(),
        vector_store,
        llm,
        min_relevance_score=0.1,
    )

    answer = await use_case.execute("¿Cuál es la presión?", doc_ids=["doc-1"])

    assert answer.text == "La presión nominal es 10 bar."
    assert answer.sufficient_info is True
    assert len(answer.sources) == 1
    assert answer.sources[0].filename == "manual.pdf"
    assert answer.sources[0].page == 2
    assert answer.sources[0].chunk_id == "chunk-1"
    assert vector_store.calls[0]["doc_ids"] == ["doc-1"]
    prompt = llm.calls[0]["prompt"]
    assert "[chunk_id: chunk-1 | fuente: manual.pdf, página: 2]" in prompt
    assert "IDs de chunks válidos para sources:\n- chunk-1" in prompt
    assert "La presión nominal es 10 bar." in prompt
    assert llm.calls[0]["system"]
    assert llm.calls[0]["json_schema"]["required"] == ["answer", "sufficient_info", "sources"]


@pytest.mark.asyncio
async def test_history_guides_retrieval_and_nearest_cited_image_is_returned() -> None:
    close_bbox = BBox(10, 12, 20, 22)
    far_bbox = BBox(10, 100, 20, 110)
    close_image = ImageRef(
        id="close",
        doc_id="doc-1",
        page=2,
        bbox=close_bbox,
        path="close.png",
    )
    far_image = ImageRef(
        id="far",
        doc_id="doc-1",
        page=2,
        bbox=far_bbox,
        path="far.png",
    )
    close_chunk = _retrieved("close-chunk", score=0.6)
    close_chunk = RetrievedChunk(
        chunk=Chunk(
            id=close_chunk.chunk.id,
            doc_id=close_chunk.chunk.doc_id,
            filename=close_chunk.chunk.filename,
            text=close_chunk.chunk.text,
            page=close_chunk.chunk.page,
            bboxes=(BBox(10, 1, 20, 5), close_bbox),
            image_ids=("close",),
        ),
        score=close_chunk.score,
    )
    far_chunk = _retrieved("far-chunk", score=0.9)
    far_chunk = RetrievedChunk(
        chunk=Chunk(
            id=far_chunk.chunk.id,
            doc_id=far_chunk.chunk.doc_id,
            filename=far_chunk.chunk.filename,
            text=far_chunk.chunk.text,
            page=far_chunk.chunk.page,
            bboxes=(BBox(10, 1, 20, 5), far_bbox),
            image_ids=("far",),
        ),
        score=far_chunk.score,
    )
    vector_store = _VectorStore([far_chunk, close_chunk])
    embeddings = _Embeddings()
    llm = _LLM(
        json.dumps(
            {
                "answer": "Está en el diagrama.",
                "sufficient_info": True,
                "sources": [{"chunk_id": "far-chunk"}, {"chunk_id": "close-chunk"}],
            }
        )
    )
    use_case = AnswerQuestionUseCase(
        embeddings,
        vector_store,
        llm,
        min_relevance_score=0.1,
        image_storage=_ImageStorage([far_image, close_image]),
    )
    history = [("user", "¿Qué muestra el diagrama?"), ("assistant", "El esquema del sistema.")]

    answer = await use_case.execute("¿Y cuál es su entrada?", history=history)

    assert "¿Qué muestra el diagrama?" in embeddings.queries[0]
    assert vector_store.calls[0]["query_text"] == embeddings.queries[0]
    assert "Historial conversacional (no es evidencia)" in llm.calls[0]["prompt"]
    assert "¿Y cuál es su entrada?" in llm.calls[0]["prompt"]
    assert answer.image == close_image


@pytest.mark.asyncio
async def test_no_relevant_chunks_returns_safe_answer_without_calling_llm() -> None:
    vector_store = _VectorStore(
        [
            _retrieved("below-threshold", score=0.09),
        ]
    )
    llm = _LLM("{}")
    use_case = AnswerQuestionUseCase(
        _Embeddings(),
        vector_store,
        llm,
        min_relevance_score=0.1,
    )

    answer = await use_case.execute("¿Cuál es la presión?")

    assert answer.sufficient_info is False
    assert answer.sources == ()
    assert answer.text
    assert llm.calls == []


@pytest.mark.asyncio
async def test_model_cannot_claim_sufficient_info_without_valid_citations() -> None:
    llm = _LLM(
        json.dumps(
            {
                "answer": "La presión es 50 bar.",
                "sufficient_info": True,
                "sources": [{"chunk_id": "not-retrieved"}],
            }
        )
    )
    use_case = AnswerQuestionUseCase(
        _Embeddings(),
        _VectorStore([_retrieved("chunk-1", score=0.8)]),
        llm,
        min_relevance_score=0.1,
    )

    answer = await use_case.execute("¿Cuál es la presión?")

    assert answer.sufficient_info is False
    assert answer.sources == ()
    assert "información suficiente" in answer.text


@pytest.mark.asyncio
async def test_invalid_structured_llm_response_is_reported() -> None:
    use_case = AnswerQuestionUseCase(
        _Embeddings(),
        _VectorStore([_retrieved("chunk-1", score=0.8)]),
        _LLM("no es JSON"),
        min_relevance_score=0.1,
    )

    with pytest.raises(ValueError, match="JSON válido"):
        await use_case.execute("¿Cuál es la presión?")
