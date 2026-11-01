"""Pipeline de ingesta de un documento subido."""

from __future__ import annotations

from pathlib import Path

from src.application.chunking import LayoutChunker
from src.application.ports.document_parser import DocumentParserPort
from src.application.ports.embeddings import EmbeddingPort
from src.application.ports.vector_store import VectorStorePort
from src.domain.jod import JobStatus
from src.domain.ports import JobRepoPort


class ProcessDocumentUseCase:
    """Orquesta parseo, chunking, embeddings e indexación con progreso persistido."""

    def __init__(
        self,
        jobs: JobRepoPort,
        parser: DocumentParserPort,
        chunker: LayoutChunker,
        embeddings: EmbeddingPort,
        vector_store: VectorStorePort,
    ) -> None:
        self._jobs = jobs
        self._parser = parser
        self._chunker = chunker
        self._embeddings = embeddings
        self._vector_store = vector_store

    async def execute(self, job_id: str, document_id: str, path: str) -> None:
        job = await self._jobs.get(job_id)
        if job is None:
            raise LookupError(f"no existe el job {job_id!r}")
        if job.document_id != document_id:
            raise ValueError(f"el documento no coincide con el job {job_id!r}")

        try:
            job.status = JobStatus.PROCESSING
            job.stage = "parsing"
            job.progress = 0
            job.error = None
            await self._jobs.save(job)
            document = self._parser.parse(
                Path(path),
                doc_id=document_id,
                filename=job.filename,
            )

            job.stage = "chunking"
            job.progress = 25
            await self._jobs.save(job)
            chunks = self._chunker.chunk(document)

            job.stage = "embedding"
            job.progress = 50
            await self._jobs.save(job)
            vectors = await self._embeddings.embed_documents([chunk.text for chunk in chunks])
            if len(vectors) != len(chunks):
                raise ValueError(
                    f"el proveedor devolvió {len(vectors)} embeddings para {len(chunks)} chunks"
                )

            job.stage = "indexing"
            job.progress = 75
            await self._jobs.save(job)
            await self._vector_store.ensure_collection()
            await self._vector_store.upsert(chunks, vectors)

            job.status = JobStatus.COMPLETED
            job.stage = "completed"
            job.progress = 100
            await self._jobs.save(job)
        except Exception as error:
            job.status = JobStatus.FAILED
            job.error = f"{type(error).__name__}: {error}"
            await self._jobs.save(job)
            raise
