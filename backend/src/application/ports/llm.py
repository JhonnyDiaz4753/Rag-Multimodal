"""Puerto del proveedor de lenguaje, texto y visión."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class LLMPort(ABC):
    """Contrato para cualquier proveedor de LLM (Ollama, OpenAI, ...)."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_schema: Mapping[str, Any] | None = None,
    ) -> str:
        """Genera texto a partir de un prompt y un system prompt opcional."""
        ...

    @abstractmethod
    async def describe_image(
        self,
        image: bytes,
        *,
        prompt: str,
        mime_type: str = "image/png",
    ) -> str:
        """Responde una pregunta sobre una imagen (captioning o VQA)."""
        ...
