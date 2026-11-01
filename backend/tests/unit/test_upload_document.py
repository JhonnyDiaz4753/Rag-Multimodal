import pytest

from src.application.upload_document import UploadDocumentUseCase
from src.domain.errors import EmptyFileError, FileTooLargeError, InvalidFileTypeError
from src.domain.jod import JobStatus
from tests.unit.fakes import FakeDispatcher, FakeJobRepo, FakeStorage

VALID_PDF = b"%PDF-1.7\n%fake content"


def build(max_bytes: int = 1024, fail_dispatch: bool = False):
    storage, jobs, dispatcher = FakeStorage(), FakeJobRepo(), FakeDispatcher(fail_dispatch)
    uc = UploadDocumentUseCase(storage, jobs, dispatcher, max_bytes)
    return uc, storage, jobs, dispatcher


@pytest.mark.asyncio
async def test_valid_pdf_creates_pending_job_and_dispatches():
    uc, storage, jobs, dispatcher = build()
    result = await uc.execute("manual.pdf", "application/pdf", VALID_PDF)

    job = await jobs.get(result.job_id)
    assert job is not None and job.status == JobStatus.PENDING
    assert result.document_id in storage.saved
    assert dispatcher.calls[0][0] == result.job_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename,ctype,content,error",
    [
        ("manual.pdf", "application/pdf", b"", EmptyFileError),
        ("manual.txt", "application/pdf", VALID_PDF, InvalidFileTypeError),
        ("manual.pdf", "text/plain", VALID_PDF, InvalidFileTypeError),
        ("manual.pdf", "application/pdf", b"not a pdf at all", InvalidFileTypeError),
        ("manual.pdf", "application/pdf", VALID_PDF + b"x" * 2000, FileTooLargeError),
    ],
)
async def test_invalid_files_are_rejected_without_side_effects(filename, ctype, content, error):
    uc, storage, jobs, dispatcher = build(max_bytes=1024)
    with pytest.raises(error):
        await uc.execute(filename, ctype, content)
    assert not storage.saved and not jobs.items and not dispatcher.calls


@pytest.mark.asyncio
async def test_dispatch_failure_marks_job_failed():
    uc, _, jobs, _ = build(fail_dispatch=True)
    with pytest.raises(ConnectionError):
        await uc.execute("manual.pdf", "application/pdf", VALID_PDF)

    (job,) = jobs.items.values()
    assert job.status == JobStatus.FAILED and job.error