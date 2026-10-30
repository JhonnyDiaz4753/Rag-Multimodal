"""Puertos de salida hacia servicios externos.

Las implementaciones concretas viven en ``src.infrastructure``.
"""

from src.application.ports.document_parser import DocumentParserPort
from src.application.ports.embeddings import EmbeddingPort
from src.application.ports.image_storage import ImageStoragePort
from src.application.ports.job_repository import JobRepoPort
from src.application.ports.llm import LLMPort
from src.application.ports.vector_store import VectorStorePort

__all__ = [
    "DocumentParserPort",
    "EmbeddingPort",
    "ImageStoragePort",
    "JobRepoPort",
    "LLMPort",
    "VectorStorePort",
]
