from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

AppEnvironment = Literal["development", "test", "production"]
LogFormat = Literal["json", "console"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LLMProvider = Literal["ollama", "openai"]
EmbeddingProvider = Literal["ollama", "openai"]


def _resolve_env_file() -> Path | None:
    """Busca el .env en la raíz del repositorio sin depender del cwd."""
    candidates = (
        Path.cwd() / ".env",
        REPO_ROOT / ".env",
        BACKEND_DIR / ".env",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


class Settings(BaseSettings):
    """Configuración inmutable y validada, leída de .env y del entorno."""

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    app_name: str = "rag-multimodal"
    app_version: str = "0.1.0"
    app_env: AppEnvironment = "development"
    debug: bool = False

    log_level: LogLevel = "INFO"
    log_format: LogFormat = "json"

    data_dir: Path = Path("./data")
    upload_dir: Path = Path("./data/uploads")
    max_upload_mb: int = Field(default=50, ge=1)
    job_ttl_seconds: int = Field(default=86400, ge=1)
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "manuals"
    min_relevance_score: float = Field(default=0.01, ge=0.0, le=1.0)
    sparse_embedding_model: str = "Qdrant/bm25"

    ollama_base_url: str = "http://localhost:11434"
    llm_provider: LLMProvider = "ollama"
    embedding_provider: EmbeddingProvider = "ollama"
    llm_model: str = "qwen2.5:7b-instruct"
    embedding_model: str = "bge-m3"
    embedding_dim: int = Field(default=1024, ge=1, le=65536)
    vision_model: str = "qwen2.5vl:7b"
    enable_image_captioning: bool = False

    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None

    @field_validator(
        "app_name",
        "app_version",
        "qdrant_collection",
        "sparse_embedding_model",
        "llm_model",
        "embedding_model",
        "vision_model",
    )
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("no puede estar vacío")
        return value

    @field_validator("redis_url")
    @classmethod
    def _validate_redis_url(cls, value: str) -> str:
        return _validate_url(value, {"redis", "rediss"}, "REDIS_URL")

    @field_validator("qdrant_url", "ollama_base_url", "openai_base_url")
    @classmethod
    def _validate_http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_url(value, {"http", "https"}, "URL")

    @field_validator("openai_base_url", "openai_api_key", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _validate_environment(self) -> Settings:
        if self.app_env == "production":
            if self.debug:
                raise ValueError("DEBUG debe ser false en production")
            if self.log_format != "json":
                raise ValueError("LOG_FORMAT debe ser json en production")

        if (self.llm_provider == "openai" or self.embedding_provider == "openai") and (
            self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip()
        ):
            raise ValueError(
                "OPENAI_API_KEY es obligatoria cuando LLM_PROVIDER o EMBEDDING_PROVIDER=openai"
            )

        return self

    @property
    def max_upload_bytes(self) -> int:
        """Tamaño máximo de subida expresado en bytes."""
        return self.max_upload_mb * 1024 * 1024


def _validate_url(value: str, allowed_schemes: set[str], field_name: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in allowed_schemes or not parsed.netloc:
        schemes = ", ".join(sorted(allowed_schemes))
        raise ValueError(f"{field_name} debe ser una URL válida con esquema {schemes}")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Devuelve una única instancia de configuración por proceso."""
    return Settings()
