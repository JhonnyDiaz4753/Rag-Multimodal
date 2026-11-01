from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.dependencies import get_job_repo
from src.api.schemas import JobStatusResponse
from src.domain.ports import JobRepoPort

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Consulta el estado de un job",
)
async def get_job_status(
    job_id: str,
    jobs: Annotated[JobRepoPort, Depends(get_job_repo)],
) -> JobStatusResponse:
    job = await jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job no encontrado",
        )
    return JobStatusResponse(
        job_id=job.id,
        status=job.status.value,
        stage=job.stage,
        progress=job.progress,
    )
