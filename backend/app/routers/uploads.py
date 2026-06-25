from zipfile import BadZipFile

from fastapi import APIRouter, HTTPException, UploadFile
from openpyxl.utils.exceptions import InvalidFileException

from app.config import settings
from app.models.schemas import UploadResponse
from app.services.platform.uploads import UploadService


router = APIRouter()
uploads = UploadService()


@router.post("/uploads")
async def upload_file(file: UploadFile) -> UploadResponse:
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="Upload exceeds maximum size")

    try:
        return uploads.save_upload(filename=file.filename or "upload", content=content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (BadZipFile, InvalidFileException) as exc:
        raise HTTPException(status_code=400, detail="Invalid upload") from exc
