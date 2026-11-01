"""Dobles de prueba para repositorios, almacenamiento y despachadores."""

from src.domain.jod import Job


class FakeJobRepo:
    def __init__(self) -> None:
        self.items: dict[str, Job] = {}

    async def save(self, job: Job) -> None:
        self.items[job.id] = job

    async def get(self, job_id: str) -> Job | None:
        return self.items.get(job_id)


class FakeStorage:
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}

    async def save(self, document_id: str, filename: str, content: bytes) -> str:
        self.saved[document_id] = content
        return f"/fake/{document_id}/original.pdf"


class FakeDispatcher:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.fail = fail

    async def dispatch_ingestion(self, job_id: str, document_id: str, path: str) -> None:
        if self.fail:
            raise ConnectionError("broker caído")
        self.calls.append((job_id, document_id, path))
