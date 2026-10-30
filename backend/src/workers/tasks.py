"""Tareas Celery.

Las tareas de ingesta y consulta se añadirán en las siguientes historias.
Este módulo existe para que ``autodiscover_tasks`` tenga un punto de entrada.
"""

from src.workers.celery_app import celery_app

__all__ = ["celery_app"]
