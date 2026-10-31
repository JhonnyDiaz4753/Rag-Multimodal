"""Adaptadores concretos de proveedores de embeddings."""

from src.infrastructure.embeddings.factory import build_embedding_adapter
from src.infrastructure.embeddings.ollama_embeddings import OllamaEmbeddingAdapter
from src.infrastructure.embeddings.openai_embeddings import OpenAIEmbeddingAdapter

__all__ = ["OllamaEmbeddingAdapter", "OpenAIEmbeddingAdapter", "build_embedding_adapter"]
