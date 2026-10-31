"""Construcción del almacén vectorial configurado."""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient

from src.application.ports.vector_store import VectorStorePort
from src.config.settings import Settings
from src.infrastructure.vector_stores.qdrant_store import QdrantVectorStore, _SparseEncoder


def build_vector_store(
    settings: Settings,
    *,
    client: AsyncQdrantClient | None = None,
    sparse_encoder: _SparseEncoder | None = None,
) -> VectorStorePort:
    """Construye el almacén Qdrant con sus ajustes de colección y sparse."""
    return QdrantVectorStore(settings, client=client, sparse_encoder=sparse_encoder)
