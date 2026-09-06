from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import (
    candidate_review_service,
    frame_analysis_job_manager,
    frame_timeline_service,
    screenshot_candidate_job_manager,
    screenshot_candidate_service,
    teaching_state_job_manager,
    teaching_state_service,
    visual_change_job_manager,
    visual_change_service,
)
from app.core.errors import AppError, ErrorCode
from app.schemas.analysis import (
    AnalysisJobError,
    AnalysisJobResponse,
    CandidateReviewResponse,
    FrameTimelineResponse,
    FrameTimelineSummary,
    ScreenshotCandidateResponse,
    ScreenshotCandidateSummary,
    StartFrameAnalysisRequest,
    StartFrameAnalysisResponse,
    StartScreenshotCandidateAnalysisRequest,
    StartScreenshotCandidateAnalysisResponse,
    StartTeachingStateAnalysisRequest,
    StartTeachingStateAnalysisResponse,
    StartVisualChangeAnalysisRequest,
    StartVisualChangeAnalysisResponse,
    TeachingStateResponse,
    TeachingStateSummary,
    UpdateCandidateDecisionRequest,
    UpdateCandidateDecisionResponse,
    VisualChangeResponse,
    VisualChangeSummary,
)
from app.services.candidate_review_service import CandidateReviewService
from app.services.frame_analysis_job_manager import FrameAnalysisJobManager
from app.services.frame_timeline_service import FrameTimelineService
from app.services.screenshot_candidate_job_manager import ScreenshotCandidateJobManager
from app.services.screenshot_candidate_service import ScreenshotCandidateService
from app.services.teaching_state_job_manager import TeachingStateJobManager
from app.services.teaching_state_service import TeachingStateService
from app.services.visual_change_job_manager import VisualChangeJobManager
from app.services.visual_change_service import VisualChangeService
from app.utils.youtube_url import validate_video_id

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _job_response(job) -> AnalysisJobResponse:
    error = None
    if job.error_code or job.error_message:
        error = AnalysisJobError(code=job.error_code or ErrorCode.INTERNAL_ERROR, message=job.error_message or job.message)
    return AnalysisJobResponse(
        job_id=job.job_id,
        video_id=job.video_id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        message=job.message,
        error=error,
    )


@router.post("/start", response_model=StartFrameAnalysisResponse)
def start_frame_analysis(payload: StartFrameAnalysisRequest, jobs: FrameAnalysisJobManager = Depends(frame_analysis_job_manager)) -> StartFrameAnalysisResponse:
    validate_video_id(payload.video_id)
    job, reused = jobs.start(payload.video_id)
    return StartFrameAnalysisResponse(job_id=job.job_id, video_id=job.video_id, status=job.status, reused_existing=reused, message=job.message)


@router.get("/jobs/{job_id}", response_model=AnalysisJobResponse)
def analysis_job_status(job_id: str, jobs: FrameAnalysisJobManager = Depends(frame_analysis_job_manager)) -> AnalysisJobResponse:
    return _job_response(jobs.get(job_id))


@router.post("/changes/start", response_model=StartVisualChangeAnalysisResponse)
def start_visual_change_analysis(payload: StartVisualChangeAnalysisRequest, jobs: VisualChangeJobManager = Depends(visual_change_job_manager)) -> StartVisualChangeAnalysisResponse:
    validate_video_id(payload.video_id)
    job, reused = jobs.start(payload.video_id)
    return StartVisualChangeAnalysisResponse(job_id=job.job_id, video_id=job.video_id, status=job.status, reused_existing=reused, message=job.message)


@router.get("/changes/jobs/{job_id}", response_model=AnalysisJobResponse)
def visual_change_job_status(job_id: str, jobs: VisualChangeJobManager = Depends(visual_change_job_manager)) -> AnalysisJobResponse:
    return _job_response(jobs.get(job_id))


@router.post("/states/start", response_model=StartTeachingStateAnalysisResponse)
def start_teaching_state_analysis(payload: StartTeachingStateAnalysisRequest, jobs: TeachingStateJobManager = Depends(teaching_state_job_manager)) -> StartTeachingStateAnalysisResponse:
    validate_video_id(payload.video_id)
    job, reused = jobs.start(payload.video_id)
    return StartTeachingStateAnalysisResponse(job_id=job.job_id, video_id=job.video_id, status=job.status, reused_existing=reused, message=job.message)


@router.get("/states/jobs/{job_id}", response_model=AnalysisJobResponse)
def teaching_state_job_status(job_id: str, jobs: TeachingStateJobManager = Depends(teaching_state_job_manager)) -> AnalysisJobResponse:
    return _job_response(jobs.get(job_id))


@router.post("/candidates/start", response_model=StartScreenshotCandidateAnalysisResponse)
def start_screenshot_candidate_analysis(payload: StartScreenshotCandidateAnalysisRequest, jobs: ScreenshotCandidateJobManager = Depends(screenshot_candidate_job_manager)) -> StartScreenshotCandidateAnalysisResponse:
    validate_video_id(payload.video_id)
    job, reused = jobs.start(payload.video_id)
    return StartScreenshotCandidateAnalysisResponse(job_id=job.job_id, video_id=job.video_id, status=job.status, reused_existing=reused, message=job.message)


@router.get("/candidates/jobs/{job_id}", response_model=AnalysisJobResponse)
def screenshot_candidate_job_status(job_id: str, jobs: ScreenshotCandidateJobManager = Depends(screenshot_candidate_job_manager)) -> AnalysisJobResponse:
    return _job_response(jobs.get(job_id))


@router.get("/{video_id}/timeline", response_model=FrameTimelineResponse)
def frame_timeline(video_id: str, timeline: FrameTimelineService = Depends(frame_timeline_service)) -> FrameTimelineResponse:
    validate_video_id(video_id)
    summary = timeline.get_summary(video_id)
    if not summary:
        raise AppError(ErrorCode.TIMELINE_NOT_FOUND, "A frame timeline has not been generated for this lecture yet.", 404)
    return FrameTimelineResponse(timeline=FrameTimelineSummary.model_validate(summary))


@router.get("/{video_id}/changes", response_model=VisualChangeResponse)
def visual_changes(video_id: str, changes: VisualChangeService = Depends(visual_change_service)) -> VisualChangeResponse:
    validate_video_id(video_id)
    summary = changes.get_summary(video_id)
    if not summary:
        raise AppError(ErrorCode.CHANGE_ANALYSIS_NOT_FOUND, "Visual change analysis has not been generated for this lecture yet.", 404)
    return VisualChangeResponse(changes=VisualChangeSummary.model_validate(summary))


@router.get("/{video_id}/states", response_model=TeachingStateResponse)
def teaching_states(video_id: str, states: TeachingStateService = Depends(teaching_state_service)) -> TeachingStateResponse:
    validate_video_id(video_id)
    summary = states.get_summary(video_id)
    if not summary:
        raise AppError(ErrorCode.TEACHING_STATES_NOT_FOUND, "Stable teaching-state analysis has not been generated for this lecture yet.", 404)
    return TeachingStateResponse(states=TeachingStateSummary.model_validate(summary))


@router.get("/{video_id}/candidates", response_model=ScreenshotCandidateResponse)
def screenshot_candidates(video_id: str, candidates: ScreenshotCandidateService = Depends(screenshot_candidate_service)) -> ScreenshotCandidateResponse:
    validate_video_id(video_id)
    summary = candidates.get_summary(video_id)
    if not summary:
        raise AppError(ErrorCode.SCREENSHOT_CANDIDATES_NOT_FOUND, "Screenshot candidates have not been generated for this lecture yet.", 404)
    return ScreenshotCandidateResponse(candidates=ScreenshotCandidateSummary.model_validate(summary))


@router.get("/{video_id}/candidate-review", response_model=CandidateReviewResponse)
def candidate_review(video_id: str, review: CandidateReviewService = Depends(candidate_review_service)) -> CandidateReviewResponse:
    validate_video_id(video_id)
    return CandidateReviewResponse.model_validate(review.get_review(video_id))


@router.put("/{video_id}/candidate-review/{candidate_index}", response_model=UpdateCandidateDecisionResponse)
def update_candidate_review(
    video_id: str,
    candidate_index: int,
    payload: UpdateCandidateDecisionRequest,
    review: CandidateReviewService = Depends(candidate_review_service),
) -> UpdateCandidateDecisionResponse:
    validate_video_id(video_id)
    return UpdateCandidateDecisionResponse.model_validate(
        review.update_decision(video_id, candidate_index, payload.selected, force=payload.force)
    )


@router.get("/{video_id}/candidates/{candidate_index}/image")
def candidate_image(video_id: str, candidate_index: int, review: CandidateReviewService = Depends(candidate_review_service)) -> Response:
    validate_video_id(video_id)
    return Response(content=review.preview_bytes(video_id, candidate_index), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
