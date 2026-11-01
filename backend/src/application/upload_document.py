import logging
import uuid
from dataclasses import dataclass

from src.domain.errors import EmptyFileError, FileTooLargeError, InvalidFileTypeError
from src.domain.jod import Job, JobStatus
from src.domain.ports import DocumentStoragePort, JobRepoPort, TaskDispatcherPort

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


@dataclass(frozen=True)
class UploadResult:
    job_id: str
    document_id: str


class UploadDocumentUseCase:
    def __init__(
        self,
        storage: DocumentStoragePort,
        jobs: JobRepoPort,
        dispatcher: TaskDispatcherPort,
        max_bytes: int,
    ) -> None:
        self._storage = storage
        self._jobs = jobs
        self._dispatcher = dispatcher
        self._max_bytes = max_bytes

    def _validate(self, filename: str, content_type: str | None, content: bytes) -> None:
        if not content:
            raise EmptyFileError("El archivo está vacío.")
        if len(content) > self._max_bytes:
            raise FileTooLargeError(
                f"El archivo excede el máximo de {self._max_bytes // (1024 * 1024)} MB."
            )
        if not filename.lower().endswith(".pdf"):
            raise InvalidFileTypeError("La extensión debe ser .pdf")
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise InvalidFileTypeError(f"Content-Type no permitido: {content_type}")
        # El header y la extensión se pueden falsear; los magic bytes no tanto.
        if not content.startswith(PDF_MAGIC):
            raise InvalidFileTypeError("El contenido no es un PDF válido.")

    async def execute(
        self, filename: str, content_type: str | None, content: bytes
    ) -> UploadResult:
        self._validate(filename, content_type, content)

        document_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())

        path = await self._storage.save(document_id, filename, content)
        job = Job(id=job_id, document_id=document_id, filename=filename)
        await self._jobs.save(job)

        try:
            await self._dispatcher.dispatch_ingestion(job_id, document_id, path)
        except Exception as exc:  # cola caída, broker no disponible...
            logger.exception("No se pudo encolar el job", extra={"job_id": job_id})
            job.status = JobStatus.FAILED
            job.error = "No se pudo encolar el procesamiento."
            await self._jobs.save(job)
            raise

        logger.info(
            "Documento recibido",
            extra={"job_id": job_id, "document_id": document_id, "upload_filename": filename},
        )
        return UploadResult(job_id=job_id, document_id=document_id)