from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_answer_question_use_case
from src.api.schemas import QueryRequest, QueryResponse, SourceResponse
from src.application.answer_question import AnswerQuestionUseCase

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse, summary="Consulta los manuales indexados")
async def query_documents(
    request: QueryRequest,
    use_case: Annotated[AnswerQuestionUseCase, Depends(get_answer_question_use_case)],
) -> QueryResponse:
    answer = await use_case.execute(
        request.question,
        top_k=request.top_k,
        doc_ids=request.doc_ids,
    )
    return QueryResponse(
        answer=answer.text,
        sufficient_info=answer.sufficient_info,
        sources=[
            SourceResponse(
                filename=source.filename,
                page=source.page,
                chunk_id=source.chunk_id,
            )
            for source in answer.sources
        ],
    )
