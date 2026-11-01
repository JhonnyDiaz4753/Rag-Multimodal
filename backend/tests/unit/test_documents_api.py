from fastapi.testclient import TestClient
from tests.unit.fakes import FakeDispatcher, FakeJobRepo, FakeStorage

from src.api.dependencies import get_upload_use_case
from src.api.main import app
from src.application.upload_document import UploadDocumentUseCase

VALID_PDF = b"%PDF-1.7\n%fake"


def _client(max_bytes: int = 1024) -> TestClient:
    uc = UploadDocumentUseCase(FakeStorage(), FakeJobRepo(), FakeDispatcher(), max_bytes)
    app.dependency_overrides[get_upload_use_case] = lambda: uc
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_upload_returns_202_with_job_id():
    r = _client().post("/documents", files={"file": ("m.pdf", VALID_PDF, "application/pdf")})
    assert r.status_code == 202
    body = r.json()
    assert body["job_id"] and body["status_url"] == f"/jobs/{body['job_id']}"


def test_non_pdf_returns_415():
    r = _client().post("/documents", files={"file": ("m.pdf", b"hola", "application/pdf")})
    assert r.status_code == 415


def test_empty_file_returns_400():
    r = _client().post("/documents", files={"file": ("m.pdf", b"", "application/pdf")})
    assert r.status_code == 400
