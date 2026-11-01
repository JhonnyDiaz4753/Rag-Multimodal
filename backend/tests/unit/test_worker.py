import asyncio
import threading

from src.config.settings import Settings
from src.infrastructure.tasks.celery_dispatcher import CeleryTaskDispatcher
from src.workers.celery_app import build_celery_app
from src.workers.tasks import process_document_task


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


def test_document_processing_task_is_registered_with_celery() -> None:
    assert process_document_task.name == "src.workers.tasks.process_document"


def test_celery_dispatcher_enqueues_without_blocking_event_loop(monkeypatch) -> None:
    calls: list[tuple[tuple[str, ...], int]] = []

    def apply_async(*, args: tuple[str, ...]) -> None:
        calls.append((args, threading.get_ident()))

    monkeypatch.setattr(process_document_task, "apply_async", apply_async)
    main_thread = threading.get_ident()

    asyncio.run(CeleryTaskDispatcher().dispatch_ingestion("job-1", "doc-1", "file.pdf"))

    assert calls[0][0] == ("job-1", "doc-1", "file.pdf")
    assert calls[0][1] != main_thread
