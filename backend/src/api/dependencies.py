"""Inyección de dependencias de la API: casos de uso, repositorios y adaptadores."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis

from src.application.answer_question import AnswerQuestionUseCase
from src.application.ports.image_storage import ImageStoragePort
from src.application.upload_document import UploadDocumentUseCase
from src.config.settings import Settings, get_settings
from src.domain.ports import JobRepoPort
from src.infrastructure.embeddings import build_embedding_adapter
from src.infrastructure.images import LocalImageStorage
from src.infrastructure.jobs.redis_job_repo import RedisJobRepo
from src.infrastructure.llm import build_llm_adapter
from src.infrastructure.storage.local_document_storage import LocalDocumentStorage
from src.infrastructure.tasks.celery_dispatcher import CeleryTaskDispatcher
from src.infrastructure.vector_stores import QdrantVectorStore

SettingsDep = Annotated[Settings, Depends(get_settings)]


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def get_upload_use_case(settings: SettingsDep) -> UploadDocumentUseCase:
    return UploadDocumentUseCase(
        storage=LocalDocumentStorage(settings.upload_dir),
        jobs=RedisJobRepo(get_redis(), settings.job_ttl_seconds),
        dispatcher=CeleryTaskDispatcher(),
        max_bytes=settings.max_upload_bytes,
    )


def get_job_repo(settings: SettingsDep) -> JobRepoPort:
    return RedisJobRepo(get_redis(), settings.job_ttl_seconds)


def get_image_storage(settings: SettingsDep) -> ImageStoragePort:
    return LocalImageStorage(settings.data_dir)


async def get_answer_question_use_case(
    settings: SettingsDep,
) -> AsyncIterator[AnswerQuestionUseCase]:
    vector_store = QdrantVectorStore(settings)
    try:
        yield AnswerQuestionUseCase(
            embeddings=build_embedding_adapter(settings),
            vector_store=vector_store,
            llm=build_llm_adapter(settings),
            min_relevance_score=settings.min_relevance_score,
            image_storage=get_image_storage(settings),
        )
    finally:
        await vector_store.close()
