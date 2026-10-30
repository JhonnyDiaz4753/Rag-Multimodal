"""Puerto del proveedor de embeddings."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class EmbeddingPort(ABC):
    """Contrato para convertir texto en vectores."""

    @abstractmethod
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Vectoriza un lote de fragmentos para indexarlos."""
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Vectoriza una consulta del usuario."""
        ...
