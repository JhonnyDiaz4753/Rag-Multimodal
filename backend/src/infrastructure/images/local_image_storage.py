"""Adaptador local que persiste las imágenes en el disco."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.application.ports.image_storage import ImageStoragePort
from src.domain.entities import BBox, ImageRef

_IMAGES_DIRNAME = "images"


class LocalImageStorage(ImageStoragePort):
    """Guarda y consulta las imágenes bajo un directorio raíz."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def save(
        self,
        *,
        doc_id: str,
        page: int,
        data: bytes,
        bbox: BBox,
        caption: str | None = None,
    ) -> ImageRef:
        ext = self._extension(data)
        image_id = hashlib.sha256(doc_id.encode("utf-8") + ext.encode("utf-8") + data).hexdigest()
        images_dir = self._root / _IMAGES_DIRNAME
        images_dir.mkdir(parents=True, exist_ok=True)
        path = images_dir / f"{image_id}.{ext}"
        path.write_bytes(data)

        ref = ImageRef(
            id=image_id, doc_id=doc_id, page=page, bbox=bbox, path=str(path), caption=caption
        )
        metadata_path = images_dir / f"{image_id}.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "page": page,
                    "bbox": {"x0": bbox.x0, "y0": bbox.y0, "x1": bbox.x1, "y1": bbox.y1},
                    "caption": caption,
                    "ext": ext,
                    "path": str(path),
                }
            ),
            encoding="utf-8",
        )
        return ref

    def get(self, image_id: str) -> ImageRef | None:
        images_dir = self._root / _IMAGES_DIRNAME
        metadata_path = images_dir / f"{image_id}.json"
        if not metadata_path.is_file():
            return None

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        bbox_data = metadata.get("bbox") or {}
        return ImageRef(
            id=image_id,
            doc_id=str(metadata.get("doc_id") or ""),
            page=int(metadata.get("page") or 0),
            bbox=BBox(
                float(bbox_data.get("x0") or 0.0),
                float(bbox_data.get("y0") or 0.0),
                float(bbox_data.get("x1") or 0.0),
                float(bbox_data.get("y1") or 0.0),
            ),
            path=str(metadata.get("path") or ""),
            caption=metadata.get("caption"),
        )

    def read(self, image_id: str) -> bytes:
        images_dir = self._root / _IMAGES_DIRNAME
        metadata_path = images_dir / f"{image_id}.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(image_id)

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        filename = f"{image_id}.{metadata.get('ext') or 'png'}"
        return (images_dir / filename).read_bytes()

    @staticmethod
    def _extension(data: bytes) -> str:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if data.startswith(b"\xff\xd8"):
            return "jpg"
        return "png"
