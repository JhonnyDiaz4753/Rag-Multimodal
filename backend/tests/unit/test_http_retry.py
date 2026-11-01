from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from structlog.contextvars import bind_contextvars, clear_contextvars

from src.config.settings import Settings
from src.infrastructure.embeddings._http import (
    HTTP_TIMEOUT,
    _request_with_retry,
)
from src.infrastructure.logging.config import configure_logging


def _response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://example.test")
    return httpx.Response(status_code, request=request)


@pytest.mark.parametrize("status_code", [429, 500, 503])
def test_http_retry_retries_rate_limit_and_server_errors(status_code: int) -> None:
    responses = [_response(status_code), _response(200)]
    calls = 0

    async def send() -> httpx.Response:
        nonlocal calls
        response = responses[calls]
        calls += 1
        return response

    async def run() -> httpx.Response:
        with (
            patch(
                "src.infrastructure.embeddings._http.asyncio.sleep",
                new_callable=AsyncMock,
            ) as sleep,
            patch("src.infrastructure.embeddings._http.random.uniform", return_value=0.1),
        ):
            response = await _request_with_retry(send)
            assert sleep.await_count == 1
            assert sleep.await_args.args == (0.1,)
            return response

    assert asyncio.run(run()).status_code == 200
    assert calls == 2


def test_http_retry_retries_timeouts_but_not_other_client_errors() -> None:
    calls = 0
    request = httpx.Request("POST", "https://example.test")

    async def send() -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("request timed out", request=request)
        return _response(200)

    async def run() -> httpx.Response:
        with patch(
            "src.infrastructure.embeddings._http.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            return await _request_with_retry(send)

    assert asyncio.run(run()).status_code == 200
    assert calls == 2

    calls = 0

    async def bad_request() -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(400)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_request_with_retry(bad_request))
    assert calls == 1


def test_http_retry_stops_after_three_transient_failures() -> None:
    calls = 0

    async def unavailable() -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(503)

    async def run() -> None:
        with patch(
            "src.infrastructure.embeddings._http.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep:
            with pytest.raises(httpx.HTTPStatusError):
                await _request_with_retry(unavailable)
            assert sleep.await_count == 2

    asyncio.run(run())
    assert calls == 3


def test_http_timeout_has_explicit_connect_and_read_limits() -> None:
    timeouts = HTTP_TIMEOUT.as_dict()

    assert timeouts["connect"] == 5.0
    assert timeouts["read"] == 30.0
    assert timeouts["write"] == 30.0
    assert timeouts["pool"] == 5.0


def test_retry_logs_include_request_and_job_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(_env_file=None, log_format="json"))
    bind_contextvars(request_id="request-123456", job_id="job-1")

    async def send() -> httpx.Response:
        return _response(503)

    async def run() -> None:
        with (
            patch(
                "src.infrastructure.embeddings._http.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch("src.infrastructure.embeddings._http.random.uniform", return_value=0.1),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await _request_with_retry(send)

    try:
        asyncio.run(run())
    finally:
        clear_contextvars()

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(records) == 2
    assert all(record["event"] == "provider.request.retrying" for record in records)
    assert all(record["request_id"] == "request-123456" for record in records)
    assert all(record["job_id"] == "job-1" for record in records)
    assert [record["next_attempt"] for record in records] == [2, 3]
