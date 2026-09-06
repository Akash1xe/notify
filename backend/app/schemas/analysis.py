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


class StartVisualChangeAnalysisRequest(BaseModel):
    video_id: str


class StartVisualChangeAnalysisResponse(BaseModel):
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


class VisualChangeSummary(BaseModel):
    video_id: str
    status: str
    compared_frame_count: int
    compared_pair_count: int
    no_change_count: int
    local_change_count: int
    structural_change_count: int
    scene_change_count: int
    change_pair_count: int
    average_change_score: float
    max_change_score: float
    max_change_frame_index: int | None
    coverage_complete: bool
    compared_every_consecutive_pair: bool
    detector_config: dict[str, float | int]
    generated_at: str
    timeline_generated_at: str


class VisualChangeResponse(BaseModel):
    status: str = "ready"
    changes: VisualChangeSummary
