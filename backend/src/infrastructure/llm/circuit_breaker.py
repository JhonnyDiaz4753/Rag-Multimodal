"""Circuit breaker compartido por los adaptadores de generación."""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx
import structlog

from src.application.ports.llm import LLMPort

logger = structlog.get_logger(__name__)

_FAILURE_THRESHOLD = 5
_RESET_TIMEOUT_SECONDS = 30.0


class CircuitOpenError(RuntimeError):
    """El proveedor LLM está temporalmente bloqueado por fallos consecutivos."""

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(f"circuit breaker del LLM abierto; reintente en {retry_after:.1f}s")


class CircuitBreakerState:
    """Estado thread-safe para un proveedor LLM dentro de un proceso."""

    def __init__(
        self,
        *,
        failure_threshold: int = _FAILURE_THRESHOLD,
        reset_timeout: float = _RESET_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold debe ser >= 1")
        if reset_timeout <= 0:
            raise ValueError("reset_timeout debe ser > 0")
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False

    def acquire(self) -> None:
        became_half_open = False
        with self._lock:
            if self._opened_at is None:
                return
            elapsed = self._clock() - self._opened_at
            if elapsed < self._reset_timeout or self._probe_in_flight:
                retry_after = max(0.0, self._reset_timeout - elapsed)
                raise CircuitOpenError(retry_after)
            self._probe_in_flight = True
            became_half_open = True
        if became_half_open:
            logger.info("llm.circuit.half_open")

    def record_success(self) -> None:
        with self._lock:
            was_open = self._opened_at is not None
            self._failures = 0
            self._opened_at = None
            self._probe_in_flight = False
        if was_open:
            logger.info("llm.circuit.closed")

    def record_transient_failure(self) -> None:
        opened = False
        with self._lock:
            if self._opened_at is not None and not self._probe_in_flight:
                return
            self._probe_in_flight = False
            self._failures += 1
            if self._failures < self._failure_threshold:
                return
            self._opened_at = self._clock()
            opened = True
            failures = self._failures
        if opened:
            logger.warning(
                "llm.circuit.opened",
                consecutive_failures=failures,
                reset_timeout_seconds=self._reset_timeout,
            )

    def release_probe(self) -> None:
        with self._lock:
            self._probe_in_flight = False


class CircuitBreakerLLMAdapter(LLMPort):
    """Protege un proveedor LLM y deja pasar un único sondeo al recuperarse."""

    def __init__(self, adapter: LLMPort, state: CircuitBreakerState) -> None:
        self._adapter = adapter
        self._state = state

    @property
    def provider_adapter(self) -> LLMPort:
        return self._adapter

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: Mapping[str, Any] | None = None,
    ) -> str:
        return await self._execute(
            lambda: self._adapter.generate(prompt, system=system, json_schema=json_schema)
        )

    async def describe_image(
        self,
        image: bytes,
        *,
        prompt: str,
        mime_type: str = "image/png",
    ) -> str:
        return await self._execute(
            lambda: self._adapter.describe_image(image, prompt=prompt, mime_type=mime_type)
        )

    async def _execute[T](self, operation: Callable[[], Awaitable[T]]) -> T:
        try:
            self._state.acquire()
        except CircuitOpenError as error:
            logger.warning(
                "llm.circuit.rejected",
                retry_after_seconds=round(error.retry_after, 1),
            )
            raise
        try:
            result = await operation()
        except (httpx.TimeoutException, httpx.HTTPStatusError) as error:
            if isinstance(error, httpx.TimeoutException) or (
                error.response.status_code == 429 or error.response.status_code >= 500
            ):
                self._state.record_transient_failure()
            else:
                self._state.record_success()
            logger.exception("llm.operation.failed", error_type=type(error).__name__)
            raise
        except Exception as error:
            self._state.record_success()
            logger.exception("llm.operation.failed", error_type=type(error).__name__)
            raise
        except BaseException:
            self._state.release_probe()
            raise
        else:
            self._state.record_success()
            logger.info("llm.operation.completed")
            return result
