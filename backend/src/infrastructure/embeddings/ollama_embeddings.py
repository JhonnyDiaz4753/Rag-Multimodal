"""Adaptador de embeddings para Ollama."""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from src.application.ports.embeddings import EmbeddingPort
from src.config.settings import Settings
from src.infrastructure.embeddings._http import _parse_vectors, _validate_texts


class OllamaEmbeddingAdapter(EmbeddingPort):
    """Genera embeddings de consultas y lotes mediante Ollama."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model = settings.embedding_model
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._client = client

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text])
        return vectors[0]

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        _validate_texts(texts)
        payload = {"model": self._model, "input": list(texts)}
        if self._client is not None:
            response = await self._client.post(f"{self._base_url}/api/embed", json=payload)
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self._base_url}/api/embed", json=payload)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("la respuesta de embeddings Ollama no es un objeto válido")
        return _parse_vectors(result.get("embeddings"), expected_count=len(texts))
