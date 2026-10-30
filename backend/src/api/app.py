from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.api.middleware import RequestContextMiddleware
from src.api.routes.health import router as health_router
from src.config.settings import Settings, get_settings
from src.infrastructure.logging.config import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logger.info(
        "application.starting",
        app_name=settings.app_name,
        app_env=settings.app_env,
        version=settings.app_version,
        llm_provider=settings.llm_provider,
    )
    yield
    logger.info("application.stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Crea la aplicación con configuración inyectable para tests."""
    settings = settings or get_settings()
    configure_logging(settings)

    is_production = settings.app_env == "production"
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        docs_url=None if is_production else "/docs",
        redoc_url=None,
        openapi_url=None if is_production else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)

    return app
