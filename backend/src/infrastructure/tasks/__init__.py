"""Adaptadores para despachar tareas de procesamiento."""

from src.infrastructure.tasks.celery_dispatcher import CeleryTaskDispatcher

__all__ = ["CeleryTaskDispatcher"]
