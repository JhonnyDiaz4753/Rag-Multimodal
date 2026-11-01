from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager

import numpy as np
import pytest
from fastembed.sparse.sparse_embedding_base import SparseEmbedding
from qdrant_client import AsyncQdrantClient

from src.config.settings import Settings
from src.domain import BBox, Chunk, ChunkKind
from src.infrastructure.vector_stores import QdrantVectorStore, build_vector_store


class _FakeSparseEncoder:
    def embed(self, documents: Sequence[str]) -> Iterable[SparseEmbedding]:
        return [self._vector(text) for text in documents]

    def query_embed(self, query: str) -> Iterable[SparseEmbedding]:
        return [self._vector(query)]

    @staticmethod
    def _vector(text: str) -> SparseEmbedding:
        indices = sorted({sum(token.encode("utf-8")) % 128 for token in re.findall(r"\w+", text)})
        return SparseEmbedding(
            values=np.ones(len(indices), dtype=np.float32),
            indices=np.array(indices, dtype=np.int32),
        )


def _chunk(chunk_id: str, doc_id: str, text: str, page: int = 1) -> Chunk:
    return Chunk(
        id=chunk_id,
        doc_id=doc_id,
        filename=f"{doc_id}.pdf",
        text=text,
        page=page,
        bboxes=(BBox(1, 2, 3, 4),),
        heading_path=("Manual",),
        image_ids=("image-1",),
        kind=ChunkKind.TEXT,
    )


def _store(client: AsyncQdrantClient) -> QdrantVectorStore:
    return QdrantVectorStore(
        Settings(
            _env_file=None,
            embedding_dim=3,
            qdrant_collection="test-chunks",
            min_relevance_score=0.01,
        ),
        client=client,
        sparse_encoder=_FakeSparseEncoder(),
    )


@asynccontextmanager
async def _memory_client() -> AsyncIterator[AsyncQdrantClient]:
    client = AsyncQdrantClient(location=":memory:")
    try:
        yield client
    finally:
        await client.close()


def test_qdrant_collection_supports_dense_and_sparse_vectors() -> None:
    async def run() -> None:
        async with _memory_client() as client:
            store = _store(client)
            await store.ensure_collection()

            info = await client.get_collection("test-chunks")
            assert info.config.params.vectors["dense"].size == 3
            assert info.config.params.vectors["dense"].distance.value == "Cosine"
            assert info.config.params.sparse_vectors["sparse"].modifier.value == "idf"
            await store.ensure_collection()

    asyncio.run(run())


def test_upsert_is_idempotent_and_replaces_document_chunks() -> None:
    async def run() -> None:
        async with _memory_client() as client:
            store = _store(client)
            await store.ensure_collection()
            first = _chunk("chunk-old", "doc-1", "outdated content")
            await store.upsert([first], [[1, 0, 0]])
            await store.upsert([first], [[1, 0, 0]])

            count = await client.count("test-chunks", exact=True)
            assert count.count == 1

            replacement = _chunk("chunk-new", "doc-1", "updated content")
            await store.upsert([replacement], [[0, 1, 0]])
            points, _ = await client.scroll("test-chunks", with_payload=True)
            assert len(points) == 1
            assert points[0].payload["chunk_id"] == "chunk-new"
            assert points[0].payload["text"] == "updated content"

    asyncio.run(run())


def test_hybrid_search_returns_domain_chunks_and_filters_documents() -> None:
    async def run() -> None:
        async with _memory_client() as client:
            store = _store(client)
            await store.ensure_collection()
            expected = _chunk("c1", "doc-1", "pressure valve parameter")
            other = _chunk("c2", "doc-2", "unrelated subject", page=2)
            await store.upsert([expected, other], [[1, 0, 0], [0, 0, 1]])

            results = await store.hybrid_search(
                query_text="pressure valve",
                query_vector=[1, 0, 0],
                top_k=2,
                doc_ids=["doc-1"],
            )
            assert len(results) == 1
            assert results[0].chunk == expected
            assert results[0].chunk.image_ids == ("image-1",)
            assert results[0].score > 0

            await store.delete_document("doc-1")
            assert (await client.count("test-chunks", exact=True)).count == 1

    asyncio.run(run())


def test_sparse_keyword_match_can_outweigh_dense_rank_in_rrf() -> None:
    async def run() -> None:
        async with _memory_client() as client:
            store = _store(client)
            await store.ensure_collection()
            lexical_match = _chunk("lexical", "doc-1", "pressure valve")
            dense_match = _chunk("dense", "doc-2", "unrelated keyword")
            await store.upsert(
                [lexical_match, dense_match],
                [[0, 1, 0], [1, 0, 0]],
            )

            results = await store.hybrid_search(
                query_text="pressure valve",
                query_vector=[1, 0, 0],
                top_k=2,
            )

            assert [result.chunk.id for result in results] == ["lexical", "dense"]
            assert results[0].score > results[1].score

    asyncio.run(run())


def test_hybrid_search_filters_results_below_rrf_relevance_threshold() -> None:
    async def run() -> None:
        async with _memory_client() as client:
            store = QdrantVectorStore(
                Settings(
                    _env_file=None,
                    embedding_dim=3,
                    qdrant_collection="test-chunks",
                    min_relevance_score=0.51,
                ),
                client=client,
                sparse_encoder=_FakeSparseEncoder(),
            )
            await store.ensure_collection()
            chunk = _chunk("c1", "doc-1", "unrelated keyword")
            await store.upsert([chunk], [[1, 0, 0]])

            results = await store.hybrid_search(
                query_text="pressure valve",
                query_vector=[1, 0, 0],
                top_k=5,
            )

            assert results == []

    asyncio.run(run())


@pytest.mark.parametrize(
    ("chunks", "vectors", "message"),
    [
        ([_chunk("c1", "doc-1", "text")], [], "un vector denso"),
        ([_chunk("c1", "doc-1", "text")], [[1, 2]], "dimensión"),
        ([_chunk("c1", "doc-1", "text")], [[1, 2, float("nan")]], "no es finito"),
    ],
)
def test_upsert_rejects_misaligned_or_invalid_dense_vectors(
    chunks: list[Chunk],
    vectors: list[list[float]],
    message: str,
) -> None:
    async def run() -> None:
        async with _memory_client() as client:
            store = _store(client)
            with pytest.raises(ValueError, match=message):
                await store.upsert(chunks, vectors)

    asyncio.run(run())


def test_vector_store_factory_returns_qdrant_adapter() -> None:
    async def run() -> None:
        async with _memory_client() as client:
            store = build_vector_store(
                Settings(_env_file=None, embedding_dim=3),
                client=client,
                sparse_encoder=_FakeSparseEncoder(),
            )

            assert isinstance(store, QdrantVectorStore)

    asyncio.run(run())
