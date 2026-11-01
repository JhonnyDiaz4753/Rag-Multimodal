from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_answer_question_use_case
from src.config.settings import Settings
from src.infrastructure.llm.circuit_breaker import CircuitOpenError


class _UnavailableAnswerUseCase:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def execute(self, *args: object, **kwargs: object) -> None:
        raise self._error


def _client_for(error: Exception) -> TestClient:
    app = create_app(Settings(_env_file=None, app_env="test", log_format="console"))
    app.dependency_overrides[get_answer_question_use_case] = lambda: _UnavailableAnswerUseCase(
        error
    )
    return TestClient(app)


def test_unavailable_provider_returns_actionable_503_and_request_id() -> None:
    request = httpx.Request("POST", "http://ollama:11434/api/embed")

    with _client_for(httpx.ConnectError("host unavailable", request=request)) as client:
        response = client.post(
            "/ask",
            json={"question": "Pregunta"},
            headers={"X-Request-ID": "frontend-ask-1234"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "El proveedor de IA no está disponible. Verifica su configuración."
    }
    assert response.headers["retry-after"] == "30"
    assert response.headers["x-request-id"] == "frontend-ask-1234"


@pytest.mark.parametrize(
    ("provider_status", "expected_status"),
    [(429, 503), (503, 503), (400, 502)],
)
def test_provider_http_errors_are_returned_as_gateway_errors(
    provider_status: int,
    expected_status: int,
) -> None:
    request = httpx.Request("POST", "http://ollama:11434/api/chat")
    response = httpx.Response(provider_status, request=request)
    error = httpx.HTTPStatusError("provider failed", request=request, response=response)

    with _client_for(error) as client:
        result = client.post("/ask", json={"question": "Pregunta"})

    assert result.status_code == expected_status
    assert result.json() == {
        "detail": f"El proveedor de IA respondió con el error HTTP {provider_status}."
    }


def test_open_circuit_returns_503_with_retry_after() -> None:
    with _client_for(CircuitOpenError(12.1)) as client:
        response = client.post("/ask", json={"question": "Pregunta"})

    assert response.status_code == 503
    assert response.headers["retry-after"] == "13"
    assert "temporalmente indisponible" in response.json()["detail"]
