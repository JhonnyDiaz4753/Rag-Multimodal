"""Adaptador que encola tareas de ingesta en Celery."""

from __future__ import annotations

import asyncio

from src.workers.tasks import process_document_task


class CeleryTaskDispatcher:
    """Encola la ingesta sin bloquear el event loop de la API."""

    async def dispatch_ingestion(self, job_id: str, document_id: str, path: str) -> None:
        await asyncio.to_thread(
            process_document_task.apply_async,
            args=(job_id, document_id, path),
        )
