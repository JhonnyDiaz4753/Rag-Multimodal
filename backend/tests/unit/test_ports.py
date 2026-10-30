"""Tests de los contratos de los puertos de salida."""

from __future__ import annotations

import inspect

import pytest

from src.application.ports import (
    DocumentParserPort,
    EmbeddingPort,
    ImageStoragePort,
    JobRepoPort,
    LLMPort,
    VectorStorePort,
)
from src.domain import Job

PORTS = (
    LLMPort,
    EmbeddingPort,
    VectorStorePort,
    DocumentParserPort,
    JobRepoPort,
    ImageStoragePort,
)

EXPECTED_METHODS = {
    LLMPort: {"generate", "describe_image"},
    EmbeddingPort: {"embed_documents", "embed_query"},
    VectorStorePort: {"ensure_collection", "upsert", "hybrid_search", "delete_document"},
    DocumentParserPort: {"parse"},
    JobRepoPort: {"save", "get"},
    ImageStoragePort: {"save", "get", "read"},
}

ASYNC_METHODS = (
    LLMPort.generate,
    LLMPort.describe_image,
    EmbeddingPort.embed_documents,
    EmbeddingPort.embed_query,
    VectorStorePort.ensure_collection,
    VectorStorePort.upsert,
    VectorStorePort.hybrid_search,
    VectorStorePort.delete_document,
)

SYNC_METHODS = (
    DocumentParserPort.parse,
    JobRepoPort.save,
    JobRepoPort.get,
    ImageStoragePort.save,
    ImageStoragePort.get,
    ImageStoragePort.read,
)


@pytest.mark.parametrize("port", PORTS)
def test_port_is_abstract(port: type) -> None:
    assert inspect.isabstract(port)
    with pytest.raises(TypeError):
        port()


@pytest.mark.parametrize(("port", "expected"), EXPECTED_METHODS.items())
def test_port_exposes_the_expected_contract(port: type, expected: set[str]) -> None:
    assert set(port.__abstractmethods__) == expected


@pytest.mark.parametrize("method", ASYNC_METHODS)
def test_remote_io_methods_are_async(method: object) -> None:
    assert inspect.iscoroutinefunction(method)


@pytest.mark.parametrize("method", SYNC_METHODS)
def test_local_io_methods_are_sync(method: object) -> None:
    assert not inspect.iscoroutinefunction(method)


class InMemoryJobRepo(JobRepoPort):
    """Implementación de prueba: demuestra que el puerto es sustituible."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def save(self, job: Job) -> None:
        self._jobs[job.id] = job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)


def test_job_repo_port_can_be_substituted() -> None:
    repo: JobRepoPort = InMemoryJobRepo()
    job = Job(id="job-1", doc_id="doc-1")

    repo.save(job)

    assert repo.get("job-1") is job
    assert repo.get("missing") is None
