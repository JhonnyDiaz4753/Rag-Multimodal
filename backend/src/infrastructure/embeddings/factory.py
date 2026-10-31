"""Selección del adaptador de embeddings según la configuración."""

from __future__ import annotations

import httpx

from src.application.ports.embeddings import EmbeddingPort
from src.config.settings import Settings
from src.infrastructure.embeddings.ollama_embeddings import OllamaEmbeddingAdapter
from src.infrastructure.embeddings.openai_embeddings import OpenAIEmbeddingAdapter


def build_embedding_adapter(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> EmbeddingPort:
    """Construye el adaptador configurado para embeddings."""
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingAdapter(settings, client=client)
    return OllamaEmbeddingAdapter(settings, client=client)
