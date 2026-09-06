from __future__ import annotations

from pydantic import BaseModel, Field
from app.models.job import JobStatus


class VideoUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class PrepareVideoRequest(VideoUrlRequest):
    video_id: str = Field(min_length=11, max_length=11)


class ValidationResponse(BaseModel):
    status: str = "valid"
    video_id: str
    normalized_url: str


class VideoMetadata(BaseModel):
    video_id: str
    title: str
    duration_seconds: int
    duration_formatted: str
    channel: str | None = None
    thumbnail_url: str | None = None
    normalized_url: str
    is_live: bool = False
    resolution: str | None = None


class MetadataResponse(BaseModel):
    status: str = "ready"
    video: VideoMetadata


class PrepareResponse(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
    reused_existing: bool
    message: str


class PreparedStatusResponse(BaseModel):
    video_id: str
    status: str
    prepared: bool
    message: str
    resolution: str | None = None
    duration_seconds: int | None = None
