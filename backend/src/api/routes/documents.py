"""Ruta /documents: subida de PDF con validación y encolado del procesamiento."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from src.api.dependencies import get_upload_use_case
from src.api.schemas import UploadResponse
from src.application.upload_document import UploadDocumentUseCase
from src.config.settings import Settings, get_settings
from src.domain.errors import EmptyFileError, FileTooLargeError, InvalidFileTypeError

router = APIRouter(prefix="/documents", tags=["documents"])

CHUNK_SIZE = 1024 * 1024


async def _read_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Lee por bloques y aborta en cuanto se excede el límite,
    sin cargar un archivo gigante completo en memoria."""
    buffer = bytearray()
    while chunk := await file.read(CHUNK_SIZE):
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"El archivo excede el máximo de {max_bytes // (1024 * 1024)} MB.",
            )
    return bytes(buffer)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadResponse,
    summary="Sube un PDF y encola su procesamiento",
)
async def upload_document(
    file: UploadFile = File(...),
    use_case: UploadDocumentUseCase = Depends(get_upload_use_case),
    settings: Settings = Depends(get_settings),
) -> UploadResponse:
    content = await _read_limited(file, settings.max_upload_bytes)

    try:
        result = await use_case.execute(
            filename=file.filename or "",
            content_type=file.content_type,
            content=content,
        )
    except InvalidFileTypeError as e:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(e)) from e
    except FileTooLargeError as e:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(e)) from e
    except EmptyFileError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e

    return UploadResponse(
        job_id=result.job_id,
        document_id=result.document_id,
        status_url=f"/jobs/{result.job_id}",
    )
