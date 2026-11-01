from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.dependencies import get_job_repo
from src.api.main import app
from src.domain.jod import Job, JobStatus


class _JobRepo:
    def __init__(self, jobs: dict[str, Job]) -> None:
        self._jobs = jobs

    async def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def save(self, job: Job) -> None:
        self._jobs[job.id] = job


def _client(jobs: dict[str, Job]) -> TestClient:
    app.dependency_overrides[get_job_repo] = lambda: _JobRepo(jobs)
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_job_status_returns_state_stage_and_progress() -> None:
    job = Job(
        id="job-1",
        document_id="doc-1",
        filename="manual.pdf",
        status=JobStatus.PROCESSING,
        stage="embedding",
        progress=50,
    )

    response = _client({"job-1": job}).get("/jobs/job-1")

    assert response.status_code == 200
    assert response.json() == {
        "job_id": "job-1",
        "status": "processing",
        "stage": "embedding",
        "progress": 50,
    }


def test_job_status_returns_404_when_job_does_not_exist() -> None:
    response = _client({}).get("/jobs/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Job no encontrado"}
