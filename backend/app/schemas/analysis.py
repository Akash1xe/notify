from __future__ import annotations

from pydantic import BaseModel

from app.models.job import JobStatus, JobType


class StartFrameAnalysisRequest(BaseModel):
    video_id: str


class StartFrameAnalysisResponse(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
    reused_existing: bool
    message: str


class AnalysisJobError(BaseModel):
    code: str
    message: str


class AnalysisJobResponse(BaseModel):
    job_id: str
    video_id: str
    job_type: JobType
    status: JobStatus
    progress: float
    message: str
    error: AnalysisJobError | None = None


class FrameTimelineSummary(BaseModel):
    video_id: str
    status: str
    frame_count: int
    fps: float
    width: int
    height: int
    duration_seconds: float
    first_timestamp_seconds: float
    last_timestamp_seconds: float
    generated_at: str


class FrameTimelineResponse(BaseModel):
    status: str = "ready"
    timeline: FrameTimelineSummary
