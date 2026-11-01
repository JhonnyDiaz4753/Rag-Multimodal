"""Pipeline de ingesta de un documento subido."""

from __future__ import annotations

from pathlib import Path

import structlog

from src.application.chunking import LayoutChunker
from src.application.ports.document_parser import DocumentParserPort
from src.application.ports.embeddings import EmbeddingPort
from src.application.ports.vector_store import VectorStorePort
from src.domain.jod import JobStatus
from src.domain.ports import JobRepoPort

logger = structlog.get_logger(__name__)
_EMBEDDING_BATCH_SIZE = 8


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
            logger.info("document.processing.started", job_id=job_id, document_id=document_id)
            job.status = JobStatus.PROCESSING
            job.stage = "parsing"
            job.progress = 0
            job.error = None
            await self._jobs.save(job)
            logger.info("document.processing.stage", job_id=job_id, stage=job.stage)
            document = self._parser.parse(
                Path(path),
                doc_id=document_id,
                filename=job.filename,
            )

            job.stage = "chunking"
            job.progress = 25
            await self._jobs.save(job)
            logger.info("document.processing.stage", job_id=job_id, stage=job.stage)
            chunks = self._chunker.chunk(document)

            job.stage = "embedding"
            job.progress = 50
            await self._jobs.save(job)
            logger.info(
                "document.processing.stage",
                job_id=job_id,
                stage=job.stage,
                chunks=len(chunks),
            )
            vectors: list[list[float]] = []
            total_batches = (len(chunks) + _EMBEDDING_BATCH_SIZE - 1) // _EMBEDDING_BATCH_SIZE
            for batch_index, start in enumerate(
                range(0, len(chunks), _EMBEDDING_BATCH_SIZE),
                start=1,
            ):
                batch = chunks[start : start + _EMBEDDING_BATCH_SIZE]
                batch_vectors = await self._embeddings.embed_documents(
                    [chunk.text for chunk in batch]
                )
                if len(batch_vectors) != len(batch):
                    raise ValueError(
                        f"el proveedor devolvió {len(batch_vectors)} embeddings para "
                        f"{len(batch)} chunks en el lote {batch_index}"
                    )
                vectors.extend(batch_vectors)

                job.progress = 50 + (24 * len(vectors) // len(chunks))
                await self._jobs.save(job)
                logger.info(
                    "document.processing.embedding_batch.completed",
                    job_id=job_id,
                    batch=batch_index,
                    total_batches=total_batches,
                    chunks_embedded=len(vectors),
                    total_chunks=len(chunks),
                    progress=job.progress,
                )

            job.stage = "indexing"
            job.progress = 75
            await self._jobs.save(job)
            logger.info("document.processing.stage", job_id=job_id, stage=job.stage)
            await self._vector_store.ensure_collection()
            await self._vector_store.upsert(chunks, vectors)

            job.status = JobStatus.COMPLETED
            job.stage = "completed"
            job.progress = 100
            await self._jobs.save(job)
            logger.info("document.processing.completed", job_id=job_id, chunks=len(chunks))
        except Exception as error:
            job.status = JobStatus.FAILED
            job.error = f"{type(error).__name__}: {error}"
            await self._jobs.save(job)
            logger.exception(
                "document.processing.failed",
                job_id=job_id,
                stage=job.stage,
                error_type=type(error).__name__,
            )
            raise
