"""Configuración de logging estructurado para API, workers y librerías externas."""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.stdlib import ProcessorFormatter
from structlog.types import Processor

from src.config.settings import Settings, get_settings

_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error")
_NOISY_LOGGERS = ("httpx", "httpcore", "httpx2", "httpcore2")


def _shared_processors() -> list[Processor]:
    """Processors comunes a structlog y a logs de terceros."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]


def _build_renderer(settings: Settings) -> Processor:
    if settings.log_format == "json":
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())


def configure_logging(settings: Settings | None = None) -> None:
    """Configura logging estructurado para API, workers y terceros.

    Es idempotente: sustituye los handlers del logger raíz para que llamadas
    repetidas (tests, reload, Celery) no dupliquen líneas.
    """
    settings = settings or get_settings()
    level = getattr(logging, settings.log_level)
    formatter = ProcessorFormatter(
        processor=_build_renderer(settings),
        foreign_pre_chain=_shared_processors(),
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    logging.captureWarnings(True)

    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    structlog.reset_defaults()
    structlog.configure(
        processors=[
            *_shared_processors(),
            ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
