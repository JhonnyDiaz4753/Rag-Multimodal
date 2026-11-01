"""Adaptador LLM para la API de OpenAI."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

import httpx

from src.application.ports.llm import LLMPort
from src.config.settings import Settings
from src.infrastructure.embeddings._http import HTTP_TIMEOUT, _retry_http_request


class OpenAILLMAdapter(LLMPort):
    """Genera texto estructurado y describe imágenes mediante OpenAI."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if settings.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY es obligatoria para el proveedor OpenAI")
        self._model = settings.llm_model
        self._api_key = settings.openai_api_key.get_secret_value()
        self._base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self._client = client

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: Mapping[str, Any] | None = None,
    ) -> str:
        messages = self._messages(prompt, system)
        response_format: dict[str, object] = {"type": "json_object"}
        if json_schema is not None:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "strict": True,
                    "schema": dict(json_schema),
                },
            }
        payload = {
            "model": self._model,
            "messages": messages,
            "response_format": response_format,
        }
        response = await self._post("/chat/completions", payload)
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError("la respuesta de chat OpenAI no contiene contenido válido") from error
        if not isinstance(content, str) or not content.strip():
            raise ValueError("OpenAI devolvió una respuesta vacía")
        return content

    async def describe_image(
        self,
        image: bytes,
        *,
        prompt: str,
        mime_type: str = "image/png",
    ) -> str:
        image_url = f"data:{mime_type};base64,{base64.b64encode(image).decode('ascii')}"
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        }
        response = await self._post("/chat/completions", payload)
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError(
                "la respuesta de visión OpenAI no contiene contenido válido"
            ) from error
        if not isinstance(content, str) or not content.strip():
            raise ValueError("OpenAI devolvió una descripción vacía")
        return content

    @staticmethod
    def _messages(prompt: str, system: str | None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    @_retry_http_request
    async def _post(self, path: str, payload: dict[str, object]) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._client is not None:
            response = await self._client.post(
                f"{self._base_url}{path}",
                json=payload,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
        else:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.post(
                    f"{self._base_url}{path}",
                    json=payload,
                    headers=headers,
                )
        response.raise_for_status()
        return response
