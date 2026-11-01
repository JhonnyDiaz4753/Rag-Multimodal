"""Selección del adaptador LLM a partir de la configuración."""

from __future__ import annotations

import threading

import httpx

from src.application.ports.llm import LLMPort
from src.config.settings import Settings
from src.infrastructure.llm.circuit_breaker import (
    CircuitBreakerLLMAdapter,
    CircuitBreakerState,
)
from src.infrastructure.llm.ollama_llm import OllamaLLMAdapter
from src.infrastructure.llm.openai_llm import OpenAILLMAdapter

_CIRCUIT_STATES: dict[tuple[str, str, str], CircuitBreakerState] = {}
_CIRCUIT_STATES_LOCK = threading.Lock()


def _circuit_state(provider_key: tuple[str, str, str]) -> CircuitBreakerState:
    with _CIRCUIT_STATES_LOCK:
        return _CIRCUIT_STATES.setdefault(provider_key, CircuitBreakerState())


def build_llm_adapter(
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> LLMPort:
    """Construye el adaptador configurado para generación."""
    if settings.llm_provider == "openai":
        adapter = OpenAILLMAdapter(settings, client=client)
        provider_key = (
            "openai",
            settings.llm_model,
            (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/"),
        )
    else:
        adapter = OllamaLLMAdapter(settings, client=client)
        provider_key = ("ollama", settings.llm_model, settings.ollama_base_url.rstrip("/"))
    state = _circuit_state(provider_key)
    return CircuitBreakerLLMAdapter(adapter, state)
