import pytest
from pydantic import ValidationError

from src.config.settings import Settings, get_settings


def test_defaults_without_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_ENV", "LOG_FORMAT", "EMBEDDING_DIM"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_name == "rag-multimodal"
    assert settings.app_env == "development"
    assert settings.log_format == "json"
    assert settings.embedding_dim == 1024
    assert settings.enable_image_captioning is False


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("EMBEDDING_DIM", "768")
    monkeypatch.setenv("ENABLE_IMAGE_CAPTIONING", "true")
    monkeypatch.setenv("QDRANT_COLLECTION", "custom-manuals")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.embedding_dim == 768
    assert settings.enable_image_captioning is True
    assert settings.qdrant_collection == "custom-manuals"


def test_invalid_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="staging")  # type: ignore[arg-type]


def test_production_rejects_debug() -> None:
    with pytest.raises(ValidationError, match="DEBUG"):
        Settings(_env_file=None, app_env="production", debug=True)


def test_production_requires_json_logs() -> None:
    with pytest.raises(ValidationError, match="LOG_FORMAT"):
        Settings(_env_file=None, app_env="production", log_format="console")


def test_openai_provider_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(_env_file=None, llm_provider="openai")


def test_invalid_redis_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match="REDIS_URL"):
        Settings(_env_file=None, redis_url="http://localhost:6379/0")


def test_settings_are_cached() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
