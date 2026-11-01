"""Tareas Celery para procesar documentos en segundo plano."""

import asyncio

from redis.asyncio import Redis

from src.application.chunking import LayoutChunker
from src.application.process_document import ProcessDocumentUseCase
from src.config.settings import get_settings
from src.infrastructure.embeddings import build_embedding_adapter
from src.infrastructure.images import LocalImageStorage
from src.infrastructure.jobs.redis_job_repo import RedisJobRepo
from src.infrastructure.parsers import PymupdfDocumentParser
from src.infrastructure.vector_stores import build_vector_store
from src.workers.celery_app import celery_app


async def _process_document(job_id: str, document_id: str, path: str) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    vector_store = None
    try:
        vector_store = build_vector_store(settings)
        use_case = ProcessDocumentUseCase(
            jobs=RedisJobRepo(redis, settings.job_ttl_seconds),
            parser=PymupdfDocumentParser(LocalImageStorage(settings.data_dir)),
            chunker=LayoutChunker(),
            embeddings=build_embedding_adapter(settings),
            vector_store=vector_store,
        )
        await use_case.execute(job_id, document_id, path)
    finally:
        try:
            if vector_store is not None:
                await vector_store.close()
        finally:
            await redis.aclose()


@celery_app.task(name="src.workers.tasks.process_document")
def process_document_task(job_id: str, document_id: str, path: str) -> None:
    """Ejecuta el pipeline síncrono de Celery sobre el caso de uso asíncrono."""
    asyncio.run(_process_document(job_id, document_id, path))


__all__ = ["celery_app", "process_document_task"]
