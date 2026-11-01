from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from src.application.ports import EmbeddingPort
from src.config.settings import Settings
from src.infrastructure.embeddings import (
    OllamaEmbeddingAdapter,
    OpenAIEmbeddingAdapter,
    build_embedding_adapter,
)
from src.infrastructure.embeddings._http import HTTP_TIMEOUT


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_ollama_embeds_documents_in_one_batch_and_embeds_query() -> None:
    requests: list[dict[str, object]] = []
    request_timeouts: list[dict[str, float]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        request_timeouts.append(request.extensions["timeout"])
        result = [[1, 2], [3, 4]][: len(payload["input"])]
        return httpx.Response(
            200,
            json={"embeddings": result},
        )

    async def run() -> tuple[list[list[float]], list[float]]:
        async with _client(handler) as client:
            adapter = OllamaEmbeddingAdapter(
                Settings(_env_file=None, embedding_model="nomic-embed-text"),
                client=client,
            )
            vectors = await adapter.embed_documents(["uno", "dos"])
            query = await adapter.embed_query("consulta")
            return vectors, query

    vectors, query = asyncio.run(run())

    assert vectors == [[1.0, 2.0], [3.0, 4.0]]
    assert query == [1.0, 2.0]
    assert requests == [
        {"model": "nomic-embed-text", "input": ["uno", "dos"]},
        {"model": "nomic-embed-text", "input": ["consulta"]},
    ]
    assert request_timeouts == [HTTP_TIMEOUT.as_dict(), HTTP_TIMEOUT.as_dict()]


def test_openai_batches_and_restores_provider_result_order() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [3, 4]},
                    {"index": 0, "embedding": [1, 2]},
                ]
            },
        )

    async def run() -> list[list[float]]:
        async with _client(handler) as client:
            adapter = OpenAIEmbeddingAdapter(
                Settings(
                    _env_file=None,
                    embedding_provider="openai",
                    openai_api_key="test-key",
                    embedding_model="text-embedding-test",
                ),
                client=client,
            )
            return await adapter.embed_documents(["uno", "dos"])

    vectors = asyncio.run(run())

    assert vectors == [[1.0, 2.0], [3.0, 4.0]]
    assert len(requests) == 1
    assert requests[0].url == "https://api.openai.com/v1/embeddings"
    assert requests[0].extensions["timeout"] == HTTP_TIMEOUT.as_dict()
    assert requests[0].headers["Authorization"].startswith("Bearer ")
    assert json.loads(requests[0].content) == {
        "model": "text-embedding-test",
        "input": ["uno", "dos"],
    }


@pytest.mark.parametrize(
    ("provider", "expected_type", "settings"),
    [
        ("ollama", OllamaEmbeddingAdapter, {}),
        (
            "openai",
            OpenAIEmbeddingAdapter,
            {"openai_api_key": "test-key"},
        ),
    ],
)
def test_factory_selects_configured_embedding_adapter(
    provider: str,
    expected_type: type,
    settings: dict[str, str],
) -> None:
    adapter = build_embedding_adapter(
        Settings(_env_file=None, embedding_provider=provider, **settings)
    )

    assert isinstance(adapter, expected_type)
    assert isinstance(adapter, EmbeddingPort)


@pytest.mark.parametrize("adapter_type", [OllamaEmbeddingAdapter, OpenAIEmbeddingAdapter])
def test_empty_batch_does_not_make_http_request(adapter_type: type) -> None:
    def fail_if_called(_: httpx.Request) -> httpx.Response:
        pytest.fail("empty batch should not issue a request")

    settings = Settings(
        _env_file=None,
        embedding_provider="openai" if adapter_type is OpenAIEmbeddingAdapter else "ollama",
        openai_api_key="test-key" if adapter_type is OpenAIEmbeddingAdapter else None,
    )

    async def run() -> list[list[float]]:
        async with _client(fail_if_called) as client:
            return await adapter_type(settings, client=client).embed_documents([])

    assert asyncio.run(run()) == []


def test_openai_rejects_malformed_batch_response() -> None:
    async def run() -> None:
        async with _client(
            lambda _: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1]}]})
        ) as client:
            adapter = OpenAIEmbeddingAdapter(
                Settings(_env_file=None, openai_api_key="test-key"),
                client=client,
            )
            await adapter.embed_documents(["uno", "dos"])

    with pytest.raises(ValueError, match="todos los resultados"):
        asyncio.run(run())


def test_settings_require_key_when_openai_embeddings_are_selected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(_env_file=None, embedding_provider="openai")
