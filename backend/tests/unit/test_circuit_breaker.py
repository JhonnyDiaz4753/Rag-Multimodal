from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from structlog.contextvars import bind_contextvars, clear_contextvars

from src.config.settings import Settings
from src.infrastructure.llm import (
    CircuitBreakerLLMAdapter,
    CircuitBreakerState,
    OllamaLLMAdapter,
    OpenAILLMAdapter,
    build_llm_adapter,
)
from src.infrastructure.llm.circuit_breaker import CircuitOpenError
from src.infrastructure.logging.config import configure_logging


class _FakeLLM:
    def __init__(self) -> None:
        self.failures: list[Exception] = []
        self.calls = 0

    async def generate(self, prompt: str, **kwargs: object) -> str:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return "ok"

    async def describe_image(
        self,
        image: bytes,
        *,
        prompt: str,
        mime_type: str = "image/png",
    ) -> str:
        return await self.generate(prompt)


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://llm.example")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("provider error", request=request, response=response)


def test_factory_wraps_both_providers_in_circuit_breaker() -> None:
    ollama = build_llm_adapter(Settings(_env_file=None, llm_provider="ollama"))
    openai = build_llm_adapter(
        Settings(_env_file=None, llm_provider="openai", openai_api_key="test-key")
    )

    assert isinstance(ollama, CircuitBreakerLLMAdapter)
    assert isinstance(ollama.provider_adapter, OllamaLLMAdapter)
    assert isinstance(openai, CircuitBreakerLLMAdapter)
    assert isinstance(openai.provider_adapter, OpenAILLMAdapter)


def test_breaker_opens_after_transient_failures_and_rejects_calls() -> None:
    fake_clock = [100.0]
    state = CircuitBreakerState(
        failure_threshold=2,
        reset_timeout=10,
        clock=lambda: fake_clock[0],
    )
    provider = _FakeLLM()
    provider.failures = [_http_error(503), httpx.ReadTimeout("timeout")]
    adapter = CircuitBreakerLLMAdapter(provider, state)

    async def run() -> None:
        for _ in range(2):
            with pytest.raises((httpx.HTTPStatusError, httpx.TimeoutException)):
                await adapter.generate("test")
        with pytest.raises(CircuitOpenError):
            await adapter.generate("test")

    asyncio.run(run())
    assert provider.calls == 2


def test_breaker_allows_one_probe_and_closes_after_recovery() -> None:
    fake_clock = [0.0]
    state = CircuitBreakerState(
        failure_threshold=1,
        reset_timeout=5,
        clock=lambda: fake_clock[0],
    )
    provider = _FakeLLM()
    adapter = CircuitBreakerLLMAdapter(provider, state)

    async def run() -> None:
        provider.failures = [_http_error(429)]
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.generate("test")

        fake_clock[0] = 5.0
        assert await adapter.generate("probe") == "ok"
        assert await adapter.generate("after recovery") == "ok"

    asyncio.run(run())
    assert provider.calls == 3


def test_breaker_allows_only_one_half_open_probe() -> None:
    fake_clock = [0.0]
    state = CircuitBreakerState(
        failure_threshold=1,
        reset_timeout=5,
        clock=lambda: fake_clock[0],
    )
    provider = _FakeLLM()
    provider.failures = [_http_error(503)]
    adapter = CircuitBreakerLLMAdapter(provider, state)

    class _BlockingLLM(_FakeLLM):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.finish = asyncio.Event()

        async def generate(self, prompt: str, **kwargs: object) -> str:
            self.calls += 1
            self.started.set()
            await self.finish.wait()
            return "recovered"

    async def run() -> None:
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.generate("trigger")

        fake_clock[0] = 5.0
        probe_provider = _BlockingLLM()
        probe_adapter = CircuitBreakerLLMAdapter(probe_provider, state)
        probe = asyncio.create_task(probe_adapter.generate("probe"))
        await probe_provider.started.wait()
        with pytest.raises(CircuitOpenError):
            await probe_adapter.generate("concurrent")
        probe_provider.finish.set()
        assert await probe == "recovered"

    asyncio.run(run())
    assert provider.calls == 1


def test_non_transient_http_error_does_not_open_breaker() -> None:
    state = CircuitBreakerState(failure_threshold=1, reset_timeout=5)
    provider = _FakeLLM()
    provider.failures = [_http_error(400)]
    adapter = CircuitBreakerLLMAdapter(provider, state)

    async def run() -> None:
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.generate("test")
        assert await adapter.generate("retry") == "ok"

    asyncio.run(run())
    assert provider.calls == 2


def test_llm_failure_logs_include_request_and_job_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(Settings(_env_file=None, log_format="json"))
    bind_contextvars(request_id="request-123456", job_id="job-1")
    provider = _FakeLLM()
    provider.failures = [_http_error(503)]
    adapter = CircuitBreakerLLMAdapter(
        provider,
        CircuitBreakerState(failure_threshold=1),
    )

    async def run() -> None:
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.generate("test")

    try:
        asyncio.run(run())
    finally:
        clear_contextvars()

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert {record["event"] for record in records} >= {
        "llm.circuit.opened",
        "llm.operation.failed",
    }
    assert all(record["request_id"] == "request-123456" for record in records)
    assert all(record["job_id"] == "job-1" for record in records)
