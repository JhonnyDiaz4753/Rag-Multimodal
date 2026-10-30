"""Adaptador de extracción de imágenes relevantes con PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from src.application.ports.image_storage import ImageStoragePort
from src.domain.entities import BBox, ImageRef

_MIN_IMAGE_PIXELS = 1024


class PymupdfImageExtractor:
    """Extrae imágenes con su bbox y página, descartando las irrelevantes."""

    def __init__(self, storage: ImageStoragePort) -> None:
        self._storage = storage

    def extract(self, pdf_path: Path, *, doc_id: str) -> tuple[ImageRef, ...]:
        refs: list[ImageRef] = []

        with pymupdf.open(str(pdf_path)) as document:
            for page_number, page in enumerate(document, start=1):
                for block in page.get_text("dict")["blocks"]:
                    if block.get("type") != 1:
                        continue
                    data = block.get("image")
                    pixel_count = int(block.get("width", 0)) * int(block.get("height", 0))
                    if not data or pixel_count < _MIN_IMAGE_PIXELS:
                        continue
                    bbox = BBox(
                        float(block["bbox"][0]),
                        float(block["bbox"][1]),
                        float(block["bbox"][2]),
                        float(block["bbox"][3]),
                    )
                    refs.append(
                        self._storage.save(
                            doc_id=doc_id,
                            page=page_number,
                            data=data,
                            bbox=bbox,
                            caption=None,
                        )
                    )

        return tuple(refs)
