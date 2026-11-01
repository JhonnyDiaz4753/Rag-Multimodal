"""Recupera contexto y genera respuestas fundamentadas con citas verificables."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import structlog

from src.application.answer_schema import ANSWER_JSON_SCHEMA
from src.application.ports.embeddings import EmbeddingPort
from src.application.ports.image_storage import ImageStoragePort
from src.application.ports.llm import LLMPort
from src.application.ports.vector_store import VectorStorePort
from src.domain.entities import Answer, ImageRef, RetrievedChunk, Source

_SYSTEM_PROMPT = (
    "Eres un asistente de consulta de manuales técnicos. Responde únicamente con información "
    "explícita en el contexto proporcionado. No inventes hechos, cifras ni fuentes. "
    "Si el contexto no permite responder, indica que no hay información suficiente y establece "
    "sufficient_info en false y deja sources vacío. Si la respuesta está fundamentada, establece "
    "sufficient_info en true y sources debe contener al menos un objeto con el chunk_id exacto "
    "que la respalda. Copia literalmente un ID válido; no uses nombres de archivo ni páginas. "
    "El historial es contexto conversacional no verificado y nunca constituye evidencia. "
    "Devuelve exclusivamente el JSON solicitado."
)
_INSUFFICIENT_ANSWER = "No encuentro información suficiente en los documentos para responder."
logger = structlog.get_logger(__name__)


class AnswerQuestionUseCase:
    """Ejecuta recuperación híbrida y generación defensiva."""

    def __init__(
        self,
        embeddings: EmbeddingPort,
        vector_store: VectorStorePort,
        llm: LLMPort,
        *,
        min_relevance_score: float,
        image_storage: ImageStoragePort | None = None,
    ) -> None:
        if not 0 <= min_relevance_score <= 1:
            raise ValueError("min_relevance_score debe estar entre 0 y 1")
        self._embeddings = embeddings
        self._vector_store = vector_store
        self._llm = llm
        self._min_relevance_score = min_relevance_score
        self._image_storage = image_storage

    async def execute(
        self,
        question: str,
        *,
        top_k: int = 5,
        doc_ids: Sequence[str] | None = None,
        history: Sequence[tuple[str, str]] = (),
    ) -> Answer:
        if not question.strip():
            raise ValueError("question no puede estar vacía")
        if top_k < 1:
            raise ValueError("top_k debe ser >= 1")
        for role, content in history:
            if role not in {"user", "assistant"} or not content.strip():
                raise ValueError("history solo acepta mensajes user/assistant no vacíos")

        retrieval_query = self._retrieval_query(question, history)
        logger.info("query.retrieval.started", top_k=top_k, history_messages=len(history))
        query_vector = await self._embeddings.embed_query(retrieval_query)
        retrieved = await self._vector_store.hybrid_search(
            query_text=retrieval_query,
            query_vector=query_vector,
            top_k=top_k,
            doc_ids=doc_ids,
        )
        relevant = [result for result in retrieved if result.score >= self._min_relevance_score]
        logger.info(
            "query.retrieval.completed",
            retrieved_chunks=len(retrieved),
            relevant_chunks=len(relevant),
        )
        if not relevant:
            logger.info("query.completed", sufficient_info=False, sources=0)
            return Answer(text=_INSUFFICIENT_ANSWER, sufficient_info=False)

        prompt = self._build_prompt(question, relevant, history)
        logger.info("query.llm.started", context_chunks=len(relevant))
        try:
            raw_response = await self._llm.generate(
                prompt,
                system=_SYSTEM_PROMPT,
                json_schema=ANSWER_JSON_SCHEMA,
            )
        except Exception:
            logger.exception("query.llm.failed", context_chunks=len(relevant))
            raise
        result = self._parse_response(raw_response)
        source_by_chunk_id = {
            item.chunk.id: Source(
                filename=item.chunk.filename,
                page=item.chunk.page,
                chunk_id=item.chunk.id,
            )
            for item in relevant
        }
        source_ids = result["sources"]
        sources = tuple(
            source_by_chunk_id[source_id]
            for source_id in dict.fromkeys(source_ids)
            if source_id in source_by_chunk_id
        )
        sufficient_info = result["sufficient_info"] and bool(sources)
        if not sufficient_info and result["sufficient_info"]:
            return Answer(text=_INSUFFICIENT_ANSWER, sufficient_info=False)
        image = (
            self._closest_image(relevant, source_ids)
            if sufficient_info and self._image_storage is not None
            else None
        )
        logger.info(
            "query.completed",
            sufficient_info=sufficient_info,
            sources=len(sources),
            image_attached=image is not None,
        )
        return Answer(
            text=result["answer"],
            sufficient_info=sufficient_info,
            sources=sources,
            image=image,
        )

    @staticmethod
    def _retrieval_query(question: str, history: Sequence[tuple[str, str]]) -> str:
        if not history:
            return question
        conversation = "\n".join(f"{role}: {content}" for role, content in history)
        return f"Conversación previa:\n{conversation}\nPregunta actual:\n{question}"

    @staticmethod
    def _build_prompt(
        question: str,
        chunks: Sequence[RetrievedChunk],
        history: Sequence[tuple[str, str]] = (),
    ) -> str:
        context = "\n\n".join(
            f"[chunk_id: {chunk.chunk.id} | fuente: {chunk.chunk.filename}, "
            f"página: {chunk.chunk.page}]\n{chunk.chunk.text}"
            for chunk in chunks
        )
        valid_chunk_ids = "\n".join(f"- {chunk.chunk.id}" for chunk in chunks)
        conversation = "\n".join(f"{role}: {content}" for role, content in history)
        history_context = (
            f"Historial conversacional (no es evidencia):\n{conversation}\n\n"
            if conversation
            else ""
        )
        return (
            f"{history_context}Contexto:\n{context}\n\n"
            f"IDs de chunks válidos para sources:\n{valid_chunk_ids}\n\n"
            f"Pregunta:\n{question}"
        )

    def _closest_image(
        self,
        chunks: Sequence[RetrievedChunk],
        source_ids: Sequence[str],
    ) -> ImageRef | None:
        if self._image_storage is None:
            return None

        cited_ids = set(source_ids)
        candidates: list[tuple[float, float, ImageRef]] = []
        for result in chunks:
            chunk = result.chunk
            if chunk.id not in cited_ids:
                continue
            images = [
                image
                for image_id in chunk.image_ids
                if (image := self._image_storage.get(image_id)) is not None
            ]
            image_bboxes = {image.bbox for image in images}
            text_bboxes = [bbox for bbox in chunk.bboxes if bbox not in image_bboxes]
            for image in images:
                distance = min(
                    (image.bbox.vertical_distance(bbox) for bbox in text_bboxes),
                    default=float("inf"),
                )
                candidates.append((distance, -result.score, image))
        return min(candidates, key=lambda candidate: candidate[:2])[2] if candidates else None

    @staticmethod
    def _parse_response(response: str) -> dict[str, Any]:
        try:
            data = json.loads(response)
        except json.JSONDecodeError as error:
            raise ValueError("el LLM devolvió una respuesta que no es JSON válido") from error
        if not isinstance(data, dict) or set(data) != {"answer", "sufficient_info", "sources"}:
            raise ValueError("la respuesta del LLM debe ser un objeto JSON")
        answer = data.get("answer")
        sufficient_info = data.get("sufficient_info")
        sources = data.get("sources")
        if (
            not isinstance(answer, str)
            or not answer.strip()
            or not isinstance(sufficient_info, bool)
            or not isinstance(sources, list)
            or any(
                not isinstance(source, dict)
                or set(source) != {"chunk_id"}
                or not isinstance(source.get("chunk_id"), str)
                or not source["chunk_id"].strip()
                for source in sources
            )
        ):
            raise ValueError(
                "la respuesta del LLM no cumple el esquema answer/sufficient_info/sources"
            )
        return {
            "answer": answer.strip(),
            "sufficient_info": sufficient_info,
            "sources": [source["chunk_id"] for source in sources],
        }
