"""Puerto de persistencia del estado de las ingestas."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities import Job


class JobRepoPort(ABC):
    """Contrato para guardar y consultar jobs por identificador."""

    @abstractmethod
    def save(self, job: Job) -> None:
        """Persiste el estado actual del job."""
        ...

    @abstractmethod
    def get(self, job_id: str) -> Job | None:
        """Devuelve el job o ``None`` si no existe."""
        ...
