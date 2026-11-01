"""Utilidades HTTP compartidas por adaptadores de embeddings."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from functools import wraps

import httpx
import structlog

HTTP_TIMEOUT = httpx.Timeout(30.0, connect=5.0, pool=5.0)
_MAX_ATTEMPTS = 3
_BASE_RETRY_DELAY_SECONDS = 0.25
_MAX_RETRY_DELAY_SECONDS = 2.0
logger = structlog.get_logger(__name__)


async def _retry_operation[T](operation: Callable[[], Awaitable[T]]) -> T:
    for attempt in range(_MAX_ATTEMPTS):
        status_code: int | None = None
        try:
            return await operation()
        except httpx.TimeoutException as error:
            if attempt == _MAX_ATTEMPTS - 1:
                raise
            retry_error: Exception = error
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            if (status_code != 429 and status_code < 500) or attempt == _MAX_ATTEMPTS - 1:
                raise
            retry_error = error

        delay_cap = min(
            _MAX_RETRY_DELAY_SECONDS,
            _BASE_RETRY_DELAY_SECONDS * (2**attempt),
        )
        delay = random.uniform(0.0, delay_cap)
        logger.warning(
            "provider.request.retrying",
            attempt=attempt + 1,
            next_attempt=attempt + 2,
            max_attempts=_MAX_ATTEMPTS,
            status_code=status_code,
            error_type=type(retry_error).__name__,
            delay_seconds=round(delay, 3),
        )
        await asyncio.sleep(delay)
    raise RuntimeError("se agotaron los intentos HTTP sin devolver una respuesta")


def _retry_http_request[**P, T](
    operation: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[T]]:
    """Reintenta únicamente errores HTTP 429/5xx y timeouts."""

    @wraps(operation)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        return await _retry_operation(lambda: operation(*args, **kwargs))

    return wrapped


async def _request_with_retry(
    send: Callable[[], Awaitable[httpx.Response]],
) -> httpx.Response:
    """Repite solo fallos HTTP 429/5xx y timeouts, con backoff exponencial y jitter."""

    async def execute() -> httpx.Response:
        response = await send()
        response.raise_for_status()
        return response

    return await _retry_operation(execute)


def _validate_texts(texts: Sequence[str]) -> None:
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("los textos para generar embeddings no pueden estar vacíos")


def _parse_vectors(values: object, *, expected_count: int) -> list[list[float]]:
    if not isinstance(values, list) or len(values) != expected_count:
        raise ValueError(
            f"el proveedor devolvió {len(values) if isinstance(values, list) else 'una respuesta inválida'} "
            f"para {expected_count} textos"
        )
    vectors: list[list[float]] = []
    for vector in values:
        if not isinstance(vector, list) or not vector:
            raise ValueError("el proveedor devolvió un embedding vacío o inválido")
        try:
            vectors.append([float(value) for value in vector])
        except (TypeError, ValueError) as error:
            raise ValueError("el proveedor devolvió valores de embedding inválidos") from error
    return vectors
