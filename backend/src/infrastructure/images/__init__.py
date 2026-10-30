"""Adaptadores de infraestructura de imágenes."""

from src.infrastructure.images.local_image_storage import LocalImageStorage
from src.infrastructure.images.pymupdf_image_extractor import PymupdfImageExtractor

__all__ = ["LocalImageStorage", "PymupdfImageExtractor"]
