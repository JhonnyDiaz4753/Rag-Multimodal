"""Puerto del almacén vectorial."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.entities import Chunk, RetrievedChunk


class VectorStorePort(ABC):
    """Contrato de una base vectorial con búsqueda híbrida."""

    @abstractmethod
    async def ensure_collection(self) -> None:
        """Crea la colección si no existe."""
        ...

    @abstractmethod
    async def upsert(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Inserta o actualiza chunks con sus vectores (listas alineadas por índice)."""
        ...

    @abstractmethod
    async def hybrid_search(
        self,
        *,
        query_text: str,
        query_vector: Sequence[float],
        top_k: int,
        doc_ids: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Combina similitud semántica y coincidencia de palabras clave."""
        ...

    @abstractmethod
    async def delete_document(self, doc_id: str) -> None:
        """Elimina todos los chunks de un documento."""
        ...
