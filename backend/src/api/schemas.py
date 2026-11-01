from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


class UploadResponse(BaseModel):
    job_id: str
    document_id: str
    status: str = "pending"
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    stage: str
    progress: int


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    doc_ids: list[str] | None = None


class SourceResponse(BaseModel):
    filename: str
    page: int
    chunk_id: str


class QueryResponse(BaseModel):
    answer: str
    sufficient_info: bool
    sources: list[SourceResponse]


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class AskRequest(BaseModel):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
    ]
    history: list[ConversationMessage] = Field(default_factory=list, max_length=20)
    top_k: int = Field(default=5, ge=1, le=50)
    doc_ids: list[str] | None = None


class AskSourceResponse(BaseModel):
    file: str
    page: int


class AskResponse(BaseModel):
    answer: str
    sources: list[AskSourceResponse]
    image: str | None = None
