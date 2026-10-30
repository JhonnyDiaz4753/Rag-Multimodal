from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config.settings import Settings


@pytest.fixture()
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        log_level="INFO",
        log_format="console",
    )


@pytest.fixture()
def client(test_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(test_settings)) as test_client:
        yield test_client
