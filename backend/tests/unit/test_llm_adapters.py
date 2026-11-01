from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Callable

import httpx
import pytest

from src.config.settings import Settings
from src.infrastructure.embeddings._http import HTTP_TIMEOUT
from src.infrastructure.llm import (
    CircuitBreakerLLMAdapter,
    OllamaLLMAdapter,
    OpenAILLMAdapter,
    build_llm_adapter,
)
from src.infrastructure.llm.ollama_llm import OLLAMA_LLM_TIMEOUT


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_ollama_generation_uses_json_schema_and_system_prompt() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": {"content": '{"answer":"42"}'}})

    async def run() -> str:
        async with _client(handler) as client:
            adapter = OllamaLLMAdapter(
                Settings(
                    _env_file=None,
                    llm_model="test-model",
                    ollama_base_url="http://localhost:11434",
                ),
                client=client,
            )
            return await adapter.generate(
                "Pregunta",
                system="Solo contexto",
                json_schema={"type": "object"},
            )

    assert asyncio.run(run()) == '{"answer":"42"}'
    assert requests[0].url == "http://localhost:11434/api/chat"
    assert requests[0].extensions["timeout"] == OLLAMA_LLM_TIMEOUT.as_dict()
    assert OLLAMA_LLM_TIMEOUT.as_dict() == {
        "connect": 5.0,
        "read": 180.0,
        "write": 180.0,
        "pool": 5.0,
    }
    payload = json.loads(requests[0].content)
    assert payload["model"] == "test-model"
    assert payload["stream"] is False
    assert payload["format"] == {"type": "object"}
    assert payload["messages"] == [
        {"role": "system", "content": "Solo contexto"},
        {"role": "user", "content": "Pregunta"},
    ]


def test_openai_generation_uses_structured_output_api() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"answer":"42"}'}}]},
        )

    async def run() -> str:
        async with _client(handler) as client:
            adapter = OpenAILLMAdapter(
                Settings(
                    _env_file=None,
                    llm_provider="openai",
                    openai_api_key="test-key",
                    llm_model="gpt-test",
                ),
                client=client,
            )
            return await adapter.generate(
                "Pregunta",
                json_schema={"type": "object", "required": ["answer"]},
            )

    assert asyncio.run(run()) == '{"answer":"42"}'
    assert requests[0].url == "https://api.openai.com/v1/chat/completions"
    assert requests[0].extensions["timeout"] == HTTP_TIMEOUT.as_dict()
    assert requests[0].headers["Authorization"].startswith("Bearer ")
    payload = json.loads(requests[0].content)
    assert payload["model"] == "gpt-test"
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "structured_response",
            "strict": True,
            "schema": {"type": "object", "required": ["answer"]},
        },
    }


def test_ollama_describes_image_with_base64_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": {"content": "Un diagrama"}})

    image = b"image bytes"

    async def run() -> str:
        async with _client(handler) as client:
            adapter = OllamaLLMAdapter(Settings(_env_file=None), client=client)
            return await adapter.describe_image(image, prompt="Describe")

    assert asyncio.run(run()) == "Un diagrama"
    payload = json.loads(requests[0].content)
    assert payload["messages"][0]["images"] == [base64.b64encode(image).decode("ascii")]


def test_openai_describes_image_with_data_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Un diagrama"}}]},
        )

    image = b"image bytes"

    async def run() -> str:
        async with _client(handler) as client:
            adapter = OpenAILLMAdapter(
                Settings(_env_file=None, openai_api_key="test-key"),
                client=client,
            )
            return await adapter.describe_image(image, prompt="Describe")

    assert asyncio.run(run()) == "Un diagrama"
    payload = json.loads(requests[0].content)
    image_url = payload["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url == f"data:image/png;base64,{base64.b64encode(image).decode('ascii')}"


def test_factory_selects_configured_llm_adapter() -> None:
    ollama = build_llm_adapter(Settings(_env_file=None, llm_provider="ollama"))
    openai = build_llm_adapter(
        Settings(_env_file=None, llm_provider="openai", openai_api_key="test-key")
    )

    assert isinstance(ollama, CircuitBreakerLLMAdapter)
    assert isinstance(ollama.provider_adapter, OllamaLLMAdapter)
    assert isinstance(openai, CircuitBreakerLLMAdapter)
    assert isinstance(openai.provider_adapter, OpenAILLMAdapter)


def test_openai_propagates_http_errors() -> None:
    async def run() -> None:
        async with _client(lambda _: httpx.Response(503)) as client:
            adapter = OpenAILLMAdapter(
                Settings(_env_file=None, openai_api_key="test-key"),
                client=client,
            )
            await adapter.generate("Pregunta")

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(run())
