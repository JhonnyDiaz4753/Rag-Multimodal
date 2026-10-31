"""Adaptador de embeddings para la API de OpenAI."""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from src.application.ports.embeddings import EmbeddingPort
from src.config.settings import Settings
from src.infrastructure.embeddings._http import _parse_vectors, _validate_texts


class OpenAIEmbeddingAdapter(EmbeddingPort):
    """Genera embeddings de consultas y lotes mediante OpenAI."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if settings.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY es obligatoria para embeddings OpenAI")
        self._model = settings.embedding_model
        self._api_key = settings.openai_api_key.get_secret_value()
        self._base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
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
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._base_url}/embeddings",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("la respuesta de embeddings OpenAI no es un objeto válido")
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("la respuesta de embeddings OpenAI no contiene data válida")
        ordered: list[object | None] = [None] * len(texts)
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("la respuesta de embeddings OpenAI contiene un elemento inválido")
            index = item.get("index")
            if not isinstance(index, int) or not 0 <= index < len(texts):
                raise ValueError("la respuesta de embeddings OpenAI contiene un índice inválido")
            if ordered[index] is not None:
                raise ValueError("la respuesta de embeddings OpenAI contiene índices duplicados")
            ordered[index] = item.get("embedding")
        if any(vector is None for vector in ordered):
            raise ValueError("la respuesta de embeddings OpenAI no contiene todos los resultados")
        return _parse_vectors(ordered, expected_count=len(texts))
