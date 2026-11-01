import logging

logger = logging.getLogger(__name__)


class NoopTaskDispatcher:
    """Placeholder: en HU-12 se reemplaza por CeleryTaskDispatcher."""

    async def dispatch_ingestion(self, job_id: str, document_id: str, path: str) -> None:
        logger.info("Tarea de ingesta pendiente de implementar", extra={"job_id": job_id})
