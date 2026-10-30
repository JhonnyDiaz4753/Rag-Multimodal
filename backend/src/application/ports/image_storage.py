"""Puerto de almacenamiento de las imágenes extraídas."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities import BBox, ImageRef


class ImageStoragePort(ABC):
    """Contrato para guardar, localizar y leer imágenes."""

    @abstractmethod
    def save(
        self,
        *,
        doc_id: str,
        page: int,
        data: bytes,
        bbox: BBox,
        caption: str | None = None,
    ) -> ImageRef:
        """Guarda la imagen y devuelve su referencia."""
        ...

    @abstractmethod
    def get(self, image_id: str) -> ImageRef | None:
        """Devuelve los metadatos de la imagen o ``None`` si no existe."""
        ...

    @abstractmethod
    def read(self, image_id: str) -> bytes:
        """Devuelve el contenido binario de la imagen."""
        ...
