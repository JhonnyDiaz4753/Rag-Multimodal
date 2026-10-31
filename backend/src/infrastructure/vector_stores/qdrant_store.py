"""Almacén Qdrant con recuperación híbrida densa y BM25 sparse."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Iterable, Sequence
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from fastembed import SparseTextEmbedding
from fastembed.sparse.sparse_embedding_base import SparseEmbedding
from qdrant_client import AsyncQdrantClient, models

from src.application.ports.vector_store import VectorStorePort
from src.config.settings import Settings
from src.domain.entities import BBox, Chunk, ChunkKind, RetrievedChunk

_DENSE_VECTOR_NAME = "dense"
_SPARSE_VECTOR_NAME = "sparse"


class _SparseEncoder(Protocol):
    def embed(self, documents: Sequence[str]) -> Iterable[SparseEmbedding]: ...

    def query_embed(self, query: str) -> Iterable[SparseEmbedding]: ...


class QdrantVectorStore(VectorStorePort):
    """Persiste chunks y combina similitud densa con sparse BM25 mediante RRF."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: AsyncQdrantClient | None = None,
        sparse_encoder: _SparseEncoder | None = None,
    ) -> None:
        self._collection = settings.qdrant_collection
        self._embedding_dim = settings.embedding_dim
        self._client = client or AsyncQdrantClient(url=settings.qdrant_url)
        self._sparse_encoder = sparse_encoder or SparseTextEmbedding(
            model_name=settings.sparse_embedding_model
        )

    async def ensure_collection(self) -> None:
        if await self._client.collection_exists(self._collection):
            collection = await self._client.get_collection(self._collection)
            vectors = collection.config.params.vectors
            sparse_vectors = collection.config.params.sparse_vectors or {}
            if (
                not isinstance(vectors, dict)
                or _DENSE_VECTOR_NAME not in vectors
                or vectors[_DENSE_VECTOR_NAME].size != self._embedding_dim
                or _SPARSE_VECTOR_NAME not in sparse_vectors
            ):
                raise ValueError(
                    f"la colección {self._collection!r} no tiene la configuración "
                    "densa/sparse esperada"
                )
            return

        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config={
                _DENSE_VECTOR_NAME: models.VectorParams(
                    size=self._embedding_dim,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                _SPARSE_VECTOR_NAME: models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=False),
                    modifier=models.Modifier.IDF,
                )
            },
        )

    async def upsert(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("debe haber exactamente un vector denso por chunk")
        if not chunks:
            return

        points: list[models.PointStruct] = []
        seen_chunk_ids: set[tuple[str, str]] = set()
        for chunk, vector in zip(chunks, vectors, strict=True):
            unique_chunk_id = (chunk.doc_id, chunk.id)
            if unique_chunk_id in seen_chunk_ids:
                raise ValueError(f"el lote contiene el chunk duplicado {chunk.id!r}")
            seen_chunk_ids.add(unique_chunk_id)
            dense_vector = [float(value) for value in vector]
            if len(dense_vector) != self._embedding_dim:
                raise ValueError(
                    f"el vector denso del chunk {chunk.id!r} tiene dimensión "
                    f"{len(dense_vector)}; se esperaba {self._embedding_dim}"
                )
            if not all(math.isfinite(value) for value in dense_vector):
                raise ValueError(f"el vector denso del chunk {chunk.id!r} no es finito")

        sparse_vectors = await asyncio.to_thread(
            lambda: list(self._sparse_encoder.embed([chunk.text for chunk in chunks]))
        )
        if len(sparse_vectors) != len(chunks):
            raise ValueError("FastEmbed no devolvió un vector sparse por chunk")

        point_ids_by_doc: dict[str, list[str]] = {}
        for chunk, dense_vector, sparse_vector in zip(chunks, vectors, sparse_vectors, strict=True):
            point_id = str(uuid5(NAMESPACE_URL, f"{chunk.doc_id}:{chunk.id}"))
            point_ids_by_doc.setdefault(chunk.doc_id, []).append(point_id)
            payload = {
                **chunk.payload,
                "chunk_id": chunk.id,
                "filename": chunk.filename,
                "text": chunk.text,
                "kind": chunk.kind.value,
            }
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        _DENSE_VECTOR_NAME: [float(value) for value in dense_vector],
                        _SPARSE_VECTOR_NAME: self._to_sparse_vector(sparse_vector),
                    },
                    payload=payload,
                )
            )

        await self._client.upsert(
            collection_name=self._collection,
            points=points,
            wait=True,
        )
        for doc_id, point_ids in point_ids_by_doc.items():
            await self._client.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="doc_id",
                                match=models.MatchValue(value=doc_id),
                            )
                        ],
                        must_not=[models.HasIdCondition(has_id=point_ids)],
                    )
                ),
                wait=True,
            )

    async def hybrid_search(
        self,
        *,
        query_text: str,
        query_vector: Sequence[float],
        top_k: int,
        doc_ids: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]:
        if top_k < 1:
            raise ValueError("top_k debe ser >= 1")
        dense_vector = [float(value) for value in query_vector]
        if len(dense_vector) != self._embedding_dim:
            raise ValueError(
                f"el vector de consulta tiene dimensión {len(dense_vector)}; "
                f"se esperaba {self._embedding_dim}"
            )
        if not all(math.isfinite(value) for value in dense_vector):
            raise ValueError("el vector de consulta debe contener valores finitos")
        if not query_text.strip():
            raise ValueError("query_text no puede estar vacío")
        if doc_ids is not None and not doc_ids:
            return []

        sparse_results = await asyncio.to_thread(
            lambda: list(self._sparse_encoder.query_embed(query_text))
        )
        if len(sparse_results) != 1:
            raise ValueError("FastEmbed debe devolver exactamente un vector sparse de consulta")
        sparse_vector = self._to_sparse_vector(sparse_results[0])
        query_filter = (
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchAny(any=list(doc_ids)),
                    )
                ]
            )
            if doc_ids is not None
            else None
        )
        prefetch_limit = max(top_k * 2, top_k)
        response = await self._client.query_points(
            collection_name=self._collection,
            prefetch=[
                models.Prefetch(
                    query=dense_vector,
                    using=_DENSE_VECTOR_NAME,
                    filter=query_filter,
                    limit=prefetch_limit,
                ),
                models.Prefetch(
                    query=sparse_vector,
                    using=_SPARSE_VECTOR_NAME,
                    filter=query_filter,
                    limit=prefetch_limit,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )
        return [self._to_retrieved_chunk(point) for point in response.points]

    async def delete_document(self, doc_id: str) -> None:
        if not doc_id.strip():
            raise ValueError("doc_id no puede estar vacío")
        await self._client.delete(
            collection_name=self._collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="doc_id",
                            match=models.MatchValue(value=doc_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

    async def close(self) -> None:
        """Cierra el cliente Qdrant."""
        await self._client.close()

    @staticmethod
    def _to_sparse_vector(vector: SparseEmbedding) -> models.SparseVector:
        indices = [int(index) for index in vector.indices]
        values = [float(value) for value in vector.values]
        if len(indices) != len(values):
            raise ValueError("el vector sparse tiene índices y valores desalineados")
        return models.SparseVector(indices=indices, values=values)

    @staticmethod
    def _to_retrieved_chunk(point: models.ScoredPoint) -> RetrievedChunk:
        payload = point.payload
        if not isinstance(payload, dict):
            raise ValueError(f"el punto Qdrant {point.id!r} no contiene payload")
        try:
            chunk = Chunk(
                id=str(payload["chunk_id"]),
                doc_id=str(payload["doc_id"]),
                filename=str(payload["filename"]),
                text=str(payload["text"]),
                page=int(payload["page"]),
                bboxes=tuple(BBox(*(float(value) for value in bbox)) for bbox in payload["bboxes"]),
                heading_path=tuple(str(value) for value in payload["heading_path"]),
                image_ids=tuple(str(value) for value in payload["image_ids"]),
                kind=ChunkKind(str(payload["kind"])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"el punto Qdrant {point.id!r} tiene payload inválido") from error
        return RetrievedChunk(chunk=chunk, score=float(point.score))
