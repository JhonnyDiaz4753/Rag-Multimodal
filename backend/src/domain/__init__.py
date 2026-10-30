"""Núcleo del negocio.

No debe depender de FastAPI, Celery, Qdrant, Ollama ni de ningún otro
detalle de infraestructura.
"""

from src.domain.entities import (
    Answer,
    BBox,
    Chunk,
    ChunkKind,
    Document,
    ImageRef,
    Job,
    JobStatus,
    Page,
    RetrievedChunk,
    Source,
    TableBlock,
    TextBlock,
)
from src.domain.errors import (
    DomainError,
    DomainValidationError,
    InvalidJobTransitionError,
)

__all__ = [
    "Answer",
    "BBox",
    "Chunk",
    "ChunkKind",
    "Document",
    "DomainError",
    "DomainValidationError",
    "ImageRef",
    "InvalidJobTransitionError",
    "Job",
    "JobStatus",
    "Page",
    "RetrievedChunk",
    "Source",
    "TableBlock",
    "TextBlock",
]
