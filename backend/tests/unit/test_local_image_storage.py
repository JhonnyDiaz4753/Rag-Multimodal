"""Tests del adaptador local de almacenamiento de imágenes."""

from __future__ import annotations

from pathlib import Path

from src.application.ports import ImageStoragePort
from src.domain import BBox, ImageRef
from src.infrastructure.images import LocalImageStorage


def test_save_writes_image_and_returns_ref(tmp_path: Path) -> None:
    storage = LocalImageStorage(tmp_path)
    ref = storage.save(
        doc_id="d1", page=2, data=b"x" * 2048, bbox=BBox(50, 200, 200, 300), caption="cap"
    )

    assert isinstance(ref, ImageRef)
    assert ref.doc_id == "d1"
    assert ref.page == 2
    assert ref.bbox == BBox(50, 200, 200, 300)
    assert ref.caption == "cap"
    assert (tmp_path / "images" / f"{ref.id}.png").is_file()
    assert storage.read(ref.id) == b"x" * 2048


def test_save_returns_stable_id_for_same_content(tmp_path: Path) -> None:
    storage = LocalImageStorage(tmp_path)
    first = storage.save(doc_id="d1", page=1, data=b"same-bytes", bbox=BBox(0, 0, 1, 1))
    second = storage.save(doc_id="d1", page=1, data=b"same-bytes", bbox=BBox(0, 0, 1, 1))

    assert first.id == second.id


def test_get_returns_saved_ref(tmp_path: Path) -> None:
    storage = LocalImageStorage(tmp_path)
    ref = storage.save(doc_id="d1", page=1, data=b"same-bytes", bbox=BBox(0, 0, 1, 1))

    assert isinstance(storage, ImageStoragePort)
    assert storage.get(ref.id) == ref


def test_get_unknown_image_returns_none(tmp_path: Path) -> None:
    assert LocalImageStorage(tmp_path).get("unknown") is None
