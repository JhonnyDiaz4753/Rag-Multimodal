"""Middleware HTTP para propagar el request_id y registrar accesos."""

from __future__ import annotations

import re
import time
import uuid
from typing import Final

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars

logger = structlog.get_logger(__name__)

_REQUEST_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_QUIET_PATHS: Final = frozenset({"/health"})


def _get_request_id(scope: Scope) -> str:
    incoming = Headers(scope=scope).get("x-request-id")
    if incoming and _REQUEST_ID_PATTERN.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


class RequestContextMiddleware:
    """Propaga un request_id y registra el acceso de forma estructurada."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _get_request_id(scope)
        clear_contextvars()
        bind_contextvars(
            request_id=request_id,
            method=scope["method"],
            path=scope["path"],
        )

        started_at = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        log_completed = logger.debug if scope["path"] in _QUIET_PATHS else logger.info

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception(
                "request.failed",
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
            raise
        else:
            log_completed(
                "request.completed",
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
        finally:
            clear_contextvars()
