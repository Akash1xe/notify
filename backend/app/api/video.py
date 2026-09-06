from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.storage import DeleteLocalResponse
from app.schemas.video import (
    MetadataResponse,
    PrepareResponse,
    PrepareVideoRequest,
    PreparedStatusResponse,
    ValidationResponse,
    VideoUrlRequest,
)
from app.services.job_manager import JobManager
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService
from app.services.youtube_service import YoutubeService
from app.api.dependencies import job_manager, prepared_video_service, storage_service, youtube_service
from app.utils.youtube_url import validate_video_id

router = APIRouter(prefix="/api/video", tags=["video"])


@router.post("/validate", response_model=ValidationResponse)
def validate_video(payload: VideoUrlRequest, youtube: YoutubeService = Depends(youtube_service)) -> ValidationResponse:
    video_id, normalized_url = youtube.validate(payload.url)
    return ValidationResponse(video_id=video_id, normalized_url=normalized_url)


@router.post("/metadata", response_model=MetadataResponse)
def video_metadata(payload: VideoUrlRequest, youtube: YoutubeService = Depends(youtube_service)) -> MetadataResponse:
    metadata = youtube.metadata(payload.url)
    return MetadataResponse(video=metadata)


@router.post("/prepare", response_model=PrepareResponse)
def prepare_video(payload: PrepareVideoRequest, jobs: JobManager = Depends(job_manager)) -> PrepareResponse:
    return jobs.start_prepare(payload.url, payload.video_id)


@router.get("/{video_id}/status", response_model=PreparedStatusResponse)
def prepared_status(video_id: str, prepared: PreparedVideoService = Depends(prepared_video_service)) -> PreparedStatusResponse:
    validate_video_id(video_id)
    existing = prepared.get_prepared_video(video_id)
    if existing:
        return PreparedStatusResponse(
            video_id=video_id,
            status="READY",
            prepared=True,
            message="Video is ready for frame analysis.",
            resolution=f"{existing.probe.height}p" if existing.probe.height else existing.resolution,
            duration_seconds=existing.duration_seconds,
        )
    return PreparedStatusResponse(
        video_id=video_id,
        status="NOT_PREPARED",
        prepared=False,
        message="Video has not been prepared locally.",
    )


@router.delete("/{video_id}/local", response_model=DeleteLocalResponse)
def delete_local_video(video_id: str, storage: StorageService = Depends(storage_service)) -> DeleteLocalResponse:
    validate_video_id(video_id)
    storage.delete_prepared_video(video_id)
    return DeleteLocalResponse(video_id=video_id)
