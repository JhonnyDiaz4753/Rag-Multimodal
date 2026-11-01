"""Construcción de la aplicación FastAPI, manejo de errores y registro de rutas."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.middleware import RequestContextMiddleware
from src.api.routes.ask import router as ask_router
from src.api.routes.documents import router as documents_router
from src.api.routes.health import router as health_router
from src.api.routes.jobs import router as jobs_router
from src.api.routes.query import router as query_router
from src.config.settings import Settings, get_settings
from src.infrastructure.llm.circuit_breaker import CircuitOpenError
from src.infrastructure.logging.config import configure_logging

logger = structlog.get_logger(__name__)


async def _handle_provider_connection_error(
    request: Request,
    error: httpx.RequestError,
) -> JSONResponse:
    logger.exception(
        "provider.connection.failed",
        path=request.url.path,
        error_type=type(error).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "El proveedor de IA no está disponible. Verifica su configuración."},
        headers={"Retry-After": "30"},
    )


async def _handle_provider_http_error(
    request: Request,
    error: httpx.HTTPStatusError,
) -> JSONResponse:
    status_code = error.response.status_code
    response_status = 503 if status_code == 429 or status_code >= 500 else 502
    logger.error(
        "provider.request.failed",
        path=request.url.path,
        provider_status_code=status_code,
        error_type=type(error).__name__,
    )
    return JSONResponse(
        status_code=response_status,
        content={"detail": f"El proveedor de IA respondió con el error HTTP {status_code}."},
        headers={"Retry-After": "30"} if response_status == 503 else {},
    )


async def _handle_open_circuit(
    request: Request,
    error: CircuitOpenError,
) -> JSONResponse:
    logger.warning(
        "provider.circuit.open",
        path=request.url.path,
        retry_after_seconds=round(error.retry_after, 1),
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "El proveedor de IA está temporalmente indisponible. Inténtalo de nuevo."
        },
        headers={"Retry-After": str(max(1, int(error.retry_after + 0.99)))},
    )


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
    app.add_exception_handler(httpx.RequestError, _handle_provider_connection_error)
    app.add_exception_handler(httpx.HTTPStatusError, _handle_provider_http_error)
    app.add_exception_handler(CircuitOpenError, _handle_open_circuit)
    app.state.settings = settings
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(jobs_router)
    app.include_router(query_router)
    app.include_router(ask_router)

    return app
