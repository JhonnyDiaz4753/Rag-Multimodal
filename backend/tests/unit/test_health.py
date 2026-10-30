from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.settings import Settings


def test_health_returns_service_metadata(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "rag-multimodal",
        "version": "0.1.0",
        "environment": "test",
    }


def test_request_id_is_generated(client: TestClient) -> None:
    response = client.get("/health")

    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32
    int(request_id, 16)


def test_incoming_request_id_is_preserved(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-123456"})

    assert response.headers["x-request-id"] == "trace-123456"


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad id"})

    assert response.headers["x-request-id"] != "bad id"


def test_docs_are_disabled_in_production() -> None:
    settings = Settings(_env_file=None, app_env="production", log_format="json")
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/health").status_code == 200
