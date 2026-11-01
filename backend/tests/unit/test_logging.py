"""Tests de la configuración de logging JSON y consola."""

import json

import pytest
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from src.config.settings import Settings
from src.infrastructure.logging.config import configure_logging


@pytest.fixture(autouse=True)
def _clean_context() -> None:
    clear_contextvars()


def test_json_logs_include_request_id_and_extra_fields(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(_env_file=None, log_format="json"))
    bind_contextvars(request_id="req-123456")

    structlog.get_logger("tests.logging").info("event.test", answer=42)

    output = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    payload = json.loads(output[-1])

    assert payload["event"] == "event.test"
    assert payload["request_id"] == "req-123456"
    assert payload["answer"] == 42
    assert payload["level"] == "info"
    assert payload["logger"] == "tests.logging"
    assert "timestamp" in payload


def test_console_logging_is_human_readable(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(_env_file=None, log_format="console"))

    structlog.get_logger("tests.logging").info("event.console", detail="visible")

    output = capsys.readouterr().out
    assert "event.console" in output
    assert "visible" in output
