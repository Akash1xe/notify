from fastapi import APIRouter, Depends

from app.api.dependencies import job_manager, storage_service
from app.schemas.storage import CleanupResponse, StorageStatusResponse
from app.services.job_manager import JobManager
from app.services.storage_service import StorageService

router = APIRouter(prefix="/api/storage", tags=["storage"])


@router.get("/status", response_model=StorageStatusResponse)
def storage_status(storage: StorageService = Depends(storage_service)) -> StorageStatusResponse:
    return StorageStatusResponse(
        prepared_video_count=storage.prepared_video_count(),
        downloads_size_bytes=storage.directory_size(storage.downloads_dir),
        temp_size_bytes=storage.directory_size(storage.temp_dir),
        output_size_bytes=storage.directory_size(storage.output_dir),
        free_space_bytes=storage.free_space_bytes(),
    )


@router.post("/cleanup", response_model=CleanupResponse)
def cleanup_storage(
    storage: StorageService = Depends(storage_service),
    jobs: JobManager = Depends(job_manager),
) -> CleanupResponse:
    removed, freed = storage.cleanup_stale(jobs.active_job_ids())
    return CleanupResponse(removed_temp_directories=removed, freed_bytes=freed)
