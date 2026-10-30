"""Puerto de extracción de contenido de PDF."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.domain.entities import Document


class DocumentParserPort(ABC):
    """Contrato de un parser multimodal (texto, tablas e imágenes)."""

    @abstractmethod
    def parse(self, pdf_path: Path, *, doc_id: str, filename: str) -> Document:
        """Extrae la estructura del PDF conservando posiciones y páginas."""
        ...
