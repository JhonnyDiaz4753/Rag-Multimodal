"""Entidades y value objects del dominio.

Solo dependen de la librería estándar: el dominio no conoce FastAPI, Celery,
Qdrant, Ollama ni ningún otro detalle de infraestructura.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite

from src.domain.errors import DomainValidationError, InvalidJobTransitionError


def _require_text(value: str, field_name: str) -> str:
    """Valida que un campo de texto no esté vacío."""
    if not value or not value.strip():
        raise DomainValidationError(f"{field_name} no puede estar vacío")
    return value


def _require_page_number(value: int) -> int:
    """Valida que un número de página sea positivo."""
    if value < 1:
        raise DomainValidationError("el número de página debe ser >= 1")
    return value


class ChunkKind(StrEnum):
    """Procedencia del contenido de un chunk."""

    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"


class JobStatus(StrEnum):
    """Estados del ciclo de vida de una ingesta."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BBox:
    """Caja envolvente en coordenadas de página."""

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.x0, self.y0, self.x1, self.y1)):
            raise DomainValidationError("las coordenadas del BBox deben ser finitas")
        if self.x0 > self.x1 or self.y0 > self.y1:
            raise DomainValidationError(
                f"BBox inválido: ({self.x0}, {self.y0}) no puede ir después de "
                f"({self.x1}, {self.y1})"
            )

    @property
    def width(self) -> float:
        """Ancho de la caja."""
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        """Alto de la caja."""
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        """Área de la caja."""
        return self.width * self.height

    def vertical_distance(self, other: BBox) -> float:
        """Distancia vertical entre dos cajas (0 si se solapan o se tocan)."""
        if self.y1 <= other.y0:
            return other.y0 - self.y1
        if other.y1 <= self.y0:
            return self.y0 - other.y1
        return 0.0

    def horizontal_distance(self, other: BBox) -> float:
        """Distancia horizontal entre dos cajas (0 si se solapan o se tocan)."""
        if self.x1 <= other.x0:
            return other.x0 - self.x1
        if other.x1 <= self.x0:
            return self.x0 - other.x1
        return 0.0

    def intersects(self, other: BBox) -> bool:
        """Indica si el área de solape es mayor que cero (tocar bordes no cuenta)."""
        return (
            self.x0 < other.x1 and other.x0 < self.x1 and self.y0 < other.y1 and other.y0 < self.y1
        )

    def union(self, other: BBox) -> BBox:
        """Caja mínima que contiene a ambas."""
        return BBox(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )


@dataclass(frozen=True, slots=True)
class ImageRef:
    """Referencia a una imagen extraída de un documento."""

    id: str
    doc_id: str
    page: int
    bbox: BBox
    path: str
    caption: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.doc_id, "doc_id")
        _require_page_number(self.page)
        _require_text(self.path, "path")


@dataclass(frozen=True, slots=True)
class TextBlock:
    """Bloque de texto con su posición y estilo, usado para chunking por layout."""

    page: int
    bbox: BBox
    text: str
    font_size: float
    is_bold: bool = False
    heading_level: int = 0

    def __post_init__(self) -> None:
        _require_page_number(self.page)
        _require_text(self.text, "text")
        if not isfinite(self.font_size) or self.font_size <= 0:
            raise DomainValidationError("font_size debe ser un número positivo")
        if self.heading_level < 0:
            raise DomainValidationError("heading_level debe ser >= 0")


@dataclass(frozen=True, slots=True)
class TableBlock:
    """Tabla extraída y convertida a Markdown."""

    page: int
    bbox: BBox
    markdown: str

    def __post_init__(self) -> None:
        _require_page_number(self.page)
        _require_text(self.markdown, "markdown")


@dataclass(frozen=True, slots=True)
class Page:
    """Contenido estructurado de una página del PDF."""

    number: int
    text_blocks: tuple[TextBlock, ...] = ()
    tables: tuple[TableBlock, ...] = ()
    images: tuple[ImageRef, ...] = ()

    def __post_init__(self) -> None:
        _require_page_number(self.number)
        for block in (*self.text_blocks, *self.tables, *self.images):
            if block.page != self.number:
                raise DomainValidationError(
                    f"el bloque de la página {block.page} no pertenece a la página {self.number}"
                )


@dataclass(frozen=True, slots=True)
class Document:
    """Resultado estructurado del parseo de un PDF."""

    doc_id: str
    filename: str
    pages: tuple[Page, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.doc_id, "doc_id")
        _require_text(self.filename, "filename")
        numbers = [page.number for page in self.pages]
        if len(numbers) != len(set(numbers)):
            raise DomainValidationError("las páginas del documento no pueden repetirse")

    @property
    def page_count(self) -> int:
        """Cantidad de páginas parseadas."""
        return len(self.pages)

    def page(self, number: int) -> Page | None:
        """Devuelve la página indicada o ``None`` si no existe."""
        return next((page for page in self.pages if page.number == number), None)


@dataclass(frozen=True, slots=True)
class Chunk:
    """Fragmento indexable con su trazabilidad hacia el PDF."""

    id: str
    doc_id: str
    filename: str
    text: str
    page: int
    bboxes: tuple[BBox, ...] = ()
    heading_path: tuple[str, ...] = ()
    image_ids: tuple[str, ...] = ()
    kind: ChunkKind = ChunkKind.TEXT

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.doc_id, "doc_id")
        _require_text(self.filename, "filename")
        _require_text(self.text, "text")
        _require_page_number(self.page)

    @property
    def payload(self) -> dict[str, object]:
        """Metadatos JSON serializables para el almacén vectorial."""
        return {
            "doc_id": self.doc_id,
            "page": self.page,
            "bboxes": [[bbox.x0, bbox.y0, bbox.x1, bbox.y1] for bbox in self.bboxes],
            "heading_path": list(self.heading_path),
            "image_ids": list(self.image_ids),
        }


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """Chunk recuperado junto a su puntuación de relevancia."""

    chunk: Chunk
    score: float

    def __post_init__(self) -> None:
        if not isfinite(self.score):
            raise DomainValidationError("score debe ser un número finito")


@dataclass(frozen=True, slots=True)
class Source:
    """Fuente citada en una respuesta."""

    filename: str
    page: int
    chunk_id: str

    def __post_init__(self) -> None:
        _require_text(self.filename, "filename")
        _require_page_number(self.page)
        _require_text(self.chunk_id, "chunk_id")


@dataclass(frozen=True, slots=True)
class Answer:
    """Respuesta del sistema RAG, con sus fuentes y contexto visual."""

    text: str
    sufficient_info: bool
    sources: tuple[Source, ...] = ()
    image: ImageRef | None = None

    def __post_init__(self) -> None:
        _require_text(self.text, "text")
        if self.sufficient_info and not self.sources:
            raise DomainValidationError(
                "una respuesta con información suficiente debe citar al menos una fuente"
            )


@dataclass(slots=True)
class Job:
    """Estado de una ingesta asíncrona."""

    id: str
    doc_id: str
    status: JobStatus = JobStatus.PENDING
    stage: str = "queued"
    progress: int = 0
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.doc_id, "doc_id")
        _require_text(self.stage, "stage")
        self._validate_progress(self.progress)

    @staticmethod
    def _validate_progress(progress: int) -> None:
        if not 0 <= progress <= 100:
            raise DomainValidationError("progress debe estar entre 0 y 100")

    def _ensure_not_terminal(self) -> None:
        if self.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            raise InvalidJobTransitionError(
                f"el job {self.id} ya está en estado {self.status.value}"
            )

    def _touch(self) -> None:
        self.updated_at = datetime.now(UTC)

    def start(self, stage: str = "processing") -> None:
        """Marca el job como en proceso."""
        if self.status is not JobStatus.PENDING:
            raise InvalidJobTransitionError(
                f"no se puede iniciar un job en estado {self.status.value}"
            )
        _require_text(stage, "stage")
        self.status = JobStatus.PROCESSING
        self.stage = stage
        self.error = None
        self._touch()

    def advance(self, progress: int, stage: str | None = None) -> None:
        """Actualiza el progreso sin permitir retrocesos."""
        if self.status is not JobStatus.PROCESSING:
            raise InvalidJobTransitionError(
                f"no se puede avanzar un job en estado {self.status.value}"
            )
        self._validate_progress(progress)
        if progress < self.progress:
            raise InvalidJobTransitionError("el progreso de un job no puede retroceder")
        if stage is not None:
            _require_text(stage, "stage")
            self.stage = stage
        self.progress = progress
        self.error = None
        self._touch()

    def complete(self) -> None:
        """Finaliza el job con éxito."""
        if self.status is not JobStatus.PROCESSING:
            raise InvalidJobTransitionError(
                f"no se puede completar un job en estado {self.status.value}"
            )
        self.status = JobStatus.COMPLETED
        self.stage = "completed"
        self.progress = 100
        self.error = None
        self._touch()

    def fail(self, error: str) -> None:
        """Finaliza el job con error."""
        self._ensure_not_terminal()
        _require_text(error, "error")
        self.status = JobStatus.FAILED
        self.stage = "failed"
        self.error = error
        self._touch()
