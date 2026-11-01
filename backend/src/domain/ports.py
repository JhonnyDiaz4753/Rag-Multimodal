from typing import Protocol

from src.domain.jod import Job


class JobRepoPort(Protocol):
    async def save(self, job: Job) -> None: ...
    async def get(self, job_id: str) -> Job | None: ...


class DocumentStoragePort(Protocol):
    async def save(self, document_id: str, filename: str, content: bytes) -> str:
        """Guarda el PDF y devuelve su ruta/URI."""
        ...


class TaskDispatcherPort(Protocol):
    async def dispatch_ingestion(self, job_id: str, document_id: str, path: str) -> None: ...
