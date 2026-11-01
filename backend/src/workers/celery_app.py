"""Configuración de la aplicación Celery y del logging del worker."""

from __future__ import annotations

from typing import Any

from celery import Celery
from celery.signals import setup_logging

from src.config.settings import Settings, get_settings
from src.infrastructure.logging.config import configure_logging


@setup_logging.connect
def _configure_celery_logging(**_: Any) -> None:
    """Usa la misma configuración de logging estructurado en el worker."""
    configure_logging()


def build_celery_app(settings: Settings | None = None) -> Celery:
    settings = settings or get_settings()
    app = Celery("rag_worker")
    app.conf.update(
        broker_url=settings.redis_url,
        result_backend=settings.redis_url,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        worker_hijack_root_logger=False,
        broker_connection_retry_on_startup=True,
        broker_connection_timeout=5,
        redis_socket_connect_timeout=5,
        redis_socket_timeout=5,
        task_default_queue="rag",
    )
    app.autodiscover_tasks(["src.workers"])
    return app


celery_app = build_celery_app()
