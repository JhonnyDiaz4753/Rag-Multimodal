"""Errores del dominio.

Son excepciones de Python: el núcleo no depende de frameworks ni de librerías
externas.
"""

from __future__ import annotations


class DomainError(Exception):
    """Error base de las reglas de negocio."""


class DomainValidationError(DomainError, ValueError):
    """Una invariante del dominio no se cumple."""


class InvalidJobTransitionError(DomainError, ValueError):
    """Se intentó una transición de estado no permitida para un ``Job``."""


class InvalidFileTypeError(DomainError):
    """El archivo no es un PDF válido."""


class FileTooLargeError(DomainError):
    """El archivo excede el tamaño máximo permitido."""


class EmptyFileError(DomainError):
    """El archivo está vacío."""
