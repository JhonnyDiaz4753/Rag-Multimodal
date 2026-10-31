"""Utilidades HTTP compartidas por adaptadores de embeddings."""

from __future__ import annotations

from collections.abc import Sequence


def _validate_texts(texts: Sequence[str]) -> None:
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("los textos para generar embeddings no pueden estar vacíos")


def _parse_vectors(values: object, *, expected_count: int) -> list[list[float]]:
    if not isinstance(values, list) or len(values) != expected_count:
        raise ValueError(
            f"el proveedor devolvió {len(values) if isinstance(values, list) else 'una respuesta inválida'} "
            f"para {expected_count} textos"
        )
    vectors: list[list[float]] = []
    for vector in values:
        if not isinstance(vector, list) or not vector:
            raise ValueError("el proveedor devolvió un embedding vacío o inválido")
        try:
            vectors.append([float(value) for value in vector])
        except (TypeError, ValueError) as error:
            raise ValueError("el proveedor devolvió valores de embedding inválidos") from error
    return vectors
