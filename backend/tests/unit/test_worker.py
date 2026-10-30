from src.config.settings import Settings
from src.workers.celery_app import build_celery_app


def test_celery_uses_application_settings() -> None:
    settings = Settings(_env_file=None, redis_url="redis://example:6379/1")
    app = build_celery_app(settings)

    assert app.conf.broker_url == "redis://example:6379/1"
    assert app.conf.result_backend == "redis://example:6379/1"
    assert app.conf.task_serializer == "json"
    assert app.conf.result_serializer == "json"
    assert app.conf.accept_content == ["json"]
    assert app.conf.timezone == "UTC"
    assert app.conf.task_default_queue == "rag"
    assert app.conf.worker_hijack_root_logger is False
