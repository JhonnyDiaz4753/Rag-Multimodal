"""Ruta /ask: respuesta conversacional con fuentes e imagen opcional."""

from __future__ import annotations

import base64
import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_answer_question_use_case, get_image_storage
from src.api.schemas import AskRequest, AskResponse, AskSourceResponse
from src.application.answer_question import AnswerQuestionUseCase
from src.application.ports.image_storage import ImageStoragePort

router = APIRouter(tags=["query"])


@router.post(
    "/ask",
    response_model=AskResponse,
    response_model_exclude_none=True,
    summary="Pregunta a los manuales indexados",
)
async def ask_documents(
    request: AskRequest,
    use_case: Annotated[AnswerQuestionUseCase, Depends(get_answer_question_use_case)],
    image_storage: Annotated[ImageStoragePort, Depends(get_image_storage)],
) -> AskResponse:
    answer = await use_case.execute(
        request.question,
        top_k=request.top_k,
        doc_ids=request.doc_ids,
        history=[(message.role, message.content) for message in request.history],
    )
    image_data = None
    if answer.image is not None:
        image_bytes = image_storage.read(answer.image.id)
        mime_type = mimetypes.guess_type(answer.image.path)[0] or "application/octet-stream"
        image_data = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"

    return AskResponse(
        answer=answer.text,
        sources=[
            AskSourceResponse(file=source.filename, page=source.page) for source in answer.sources
        ],
        image=image_data,
    )
