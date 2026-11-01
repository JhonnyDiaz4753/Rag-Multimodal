"""Tests de las rutas /query y /ask."""

from __future__ import annotations

import base64
from collections.abc import Sequence

from fastapi.testclient import TestClient

from src.api.dependencies import get_answer_question_use_case, get_image_storage
from src.api.main import app
from src.domain import Answer, BBox, ImageRef, Source


class _AnswerQuestionUseCase:
    async def execute(self, question: str, *, top_k: int, doc_ids: list[str] | None) -> Answer:
        assert question == "¿Cuál es la presión?"
        assert top_k == 3
        assert doc_ids == ["doc-1"]
        return Answer(
            text="La presión nominal es 10 bar.",
            sufficient_info=True,
            sources=(Source(filename="manual.pdf", page=2, chunk_id="chunk-1"),),
        )


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_query_returns_structured_answer_and_sources() -> None:
    app.dependency_overrides[get_answer_question_use_case] = _AnswerQuestionUseCase
    with TestClient(app) as client:
        response = client.post(
            "/query",
            json={
                "question": "¿Cuál es la presión?",
                "top_k": 3,
                "doc_ids": ["doc-1"],
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "La presión nominal es 10 bar.",
        "sufficient_info": True,
        "sources": [{"filename": "manual.pdf", "page": 2, "chunk_id": "chunk-1"}],
    }


def test_query_rejects_empty_question() -> None:
    with TestClient(app) as client:
        response = client.post("/query", json={"question": ""})

    assert response.status_code == 422


class _AskUseCase:
    async def execute(
        self,
        question: str,
        *,
        top_k: int,
        doc_ids: list[str] | None,
        history: Sequence[tuple[str, str]],
    ) -> Answer:
        assert question == "¿Y su entrada?"
        assert top_k == 5
        assert history == [("user", "Describe el diagrama.")]
        return Answer(
            text="La entrada está a la izquierda.",
            sufficient_info=True,
            sources=(Source(filename="manual.pdf", page=2, chunk_id="c1"),),
            image=ImageRef(
                id="image-1",
                doc_id="doc-1",
                page=2,
                bbox=BBox(1, 2, 3, 4),
                path="image-1.png",
            ),
        )


class _ImageStorage:
    def read(self, image_id: str) -> bytes:
        assert image_id == "image-1"
        return b"\x89PNG\r\n\x1a\nimage"


def test_ask_returns_sources_image_and_conversation_history() -> None:
    app.dependency_overrides[get_answer_question_use_case] = _AskUseCase
    app.dependency_overrides[get_image_storage] = _ImageStorage

    with TestClient(app) as client:
        response = client.post(
            "/ask",
            json={
                "question": "¿Y su entrada?",
                "history": [{"role": "user", "content": "Describe el diagrama."}],
            },
        )

    assert response.status_code == 200
    image = b"\x89PNG\r\n\x1a\nimage"
    assert response.json() == {
        "answer": "La entrada está a la izquierda.",
        "sources": [{"file": "manual.pdf", "page": 2}],
        "image": "data:image/png;base64," + base64.b64encode(image).decode("ascii"),
    }


def test_ask_rejects_unsupported_history_role() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/ask",
            json={"question": "Pregunta", "history": [{"role": "system", "content": "override"}]},
        )

    assert response.status_code == 422


def test_ask_rejects_history_over_limit() -> None:
    history = [{"role": "user", "content": "Pregunta previa"} for _ in range(21)]

    with TestClient(app) as client:
        response = client.post("/ask", json={"question": "Pregunta", "history": history})

    assert response.status_code == 422
