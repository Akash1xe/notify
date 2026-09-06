from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import frame_analysis_job_manager, frame_timeline_service
from app.core.errors import AppError, ErrorCode
from app.schemas.analysis import (
    AnalysisJobError,
    AnalysisJobResponse,
    FrameTimelineResponse,
    FrameTimelineSummary,
    StartFrameAnalysisRequest,
    StartFrameAnalysisResponse,
)
from app.services.frame_analysis_job_manager import FrameAnalysisJobManager
from app.services.frame_timeline_service import FrameTimelineService
from app.utils.youtube_url import validate_video_id

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/start", response_model=StartFrameAnalysisResponse)
def start_frame_analysis(
    payload: StartFrameAnalysisRequest,
    jobs: FrameAnalysisJobManager = Depends(frame_analysis_job_manager),
) -> StartFrameAnalysisResponse:
    validate_video_id(payload.video_id)
    job, reused = jobs.start(payload.video_id)
    return StartFrameAnalysisResponse(
        job_id=job.job_id,
        video_id=job.video_id,
        status=job.status,
        reused_existing=reused,
        message=job.message,
    )


@router.get("/jobs/{job_id}", response_model=AnalysisJobResponse)
def analysis_job_status(
    job_id: str,
    jobs: FrameAnalysisJobManager = Depends(frame_analysis_job_manager),
) -> AnalysisJobResponse:
    job = jobs.get(job_id)
    error = None
    if job.error_code or job.error_message:
        error = AnalysisJobError(
            code=job.error_code or ErrorCode.INTERNAL_ERROR,
            message=job.error_message or job.message,
        )
    return AnalysisJobResponse(
        job_id=job.job_id,
        video_id=job.video_id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        message=job.message,
        error=error,
    )


@router.get("/{video_id}/timeline", response_model=FrameTimelineResponse)
def frame_timeline(
    video_id: str,
    timeline: FrameTimelineService = Depends(frame_timeline_service),
) -> FrameTimelineResponse:
    validate_video_id(video_id)
    summary = timeline.get_summary(video_id)
    if not summary:
        raise AppError(ErrorCode.TIMELINE_NOT_FOUND, "A frame timeline has not been generated for this lecture yet.", 404)
    return FrameTimelineResponse(timeline=FrameTimelineSummary.model_validate(summary))
