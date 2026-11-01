"""Adaptador LLM para Ollama."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

import httpx

from src.application.ports.llm import LLMPort
from src.config.settings import Settings


class OllamaLLMAdapter(LLMPort):
    """Genera texto estructurado y describe imágenes mediante Ollama."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model = settings.llm_model
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._client = client

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: Mapping[str, Any] | None = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "format": dict(json_schema) if json_schema is not None else "json",
        }
        response = await self._post(payload)
        try:
            content = response.json()["message"]["content"]
        except (KeyError, TypeError) as error:
            raise ValueError("la respuesta de Ollama no contiene contenido válido") from error
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama devolvió una respuesta vacía")
        return content

    async def describe_image(
        self,
        image: bytes,
        *,
        prompt: str,
        mime_type: str = "image/png",
    ) -> str:
        del mime_type
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64.b64encode(image).decode("ascii")],
                }
            ],
            "stream": False,
        }
        response = await self._post(payload)
        try:
            content = response.json()["message"]["content"]
        except (KeyError, TypeError) as error:
            raise ValueError(
                "la respuesta de visión Ollama no contiene contenido válido"
            ) from error
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama devolvió una descripción vacía")
        return content

    async def _post(self, payload: dict[str, object]) -> httpx.Response:
        if self._client is not None:
            response = await self._client.post(f"{self._base_url}/api/chat", json=payload)
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
        response.raise_for_status()
        return response
