from fastapi import APIRouter, Depends

from app.api.dependencies import media_service, ocr_service, storage_service
from app.schemas.system import SystemStatusResponse
from app.services.media_service import MediaService
from app.services.ocr_service import OcrService
from app.services.storage_service import StorageService

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def system_status(
    media: MediaService = Depends(media_service),
    ocr: OcrService = Depends(ocr_service),
    storage: StorageService = Depends(storage_service),
) -> SystemStatusResponse:
    return SystemStatusResponse(
        ffmpeg_available=bool(media.ffmpeg_path),
        ffprobe_available=bool(media.ffprobe_path),
        tesseract_available=ocr.available,
        download_directory_writable=storage.is_writable(storage.downloads_dir),
        temp_directory_writable=storage.is_writable(storage.temp_dir),
    )
