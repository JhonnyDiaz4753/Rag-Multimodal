"""Selección del adaptador LLM a partir de la configuración."""

from __future__ import annotations

import httpx

from src.application.ports.llm import LLMPort
from src.config.settings import Settings
from src.infrastructure.llm.ollama_llm import OllamaLLMAdapter
from src.infrastructure.llm.openai_llm import OpenAILLMAdapter


def build_llm_adapter(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> LLMPort:
    """Construye el adaptador configurado para generación."""
    if settings.llm_provider == "openai":
        return OpenAILLMAdapter(settings, client=client)
    return OllamaLLMAdapter(settings, client=client)
