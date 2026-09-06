from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import coverage_job_manager, coverage_service
from app.core.errors import AppError, ErrorCode
from app.schemas.analysis import AnalysisJobError, AnalysisJobResponse
from app.schemas.coverage import CoverageResultResponse, StartCoverageAuditRequest, StartCoverageAuditResponse
from app.services.coverage_job_manager import CoverageJobManager
from app.services.coverage_service import CoverageService
from app.utils.youtube_url import validate_video_id

router = APIRouter(prefix="/api/analysis", tags=["coverage"])


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


@router.post("/coverage/start", response_model=StartCoverageAuditResponse)
def start_coverage_audit(
    payload: StartCoverageAuditRequest,
    jobs: CoverageJobManager = Depends(coverage_job_manager),
) -> StartCoverageAuditResponse:
    validate_video_id(payload.video_id)
    job, reused = jobs.start(payload.video_id)
    return StartCoverageAuditResponse(
        job_id=job.job_id,
        video_id=job.video_id,
        status=job.status,
        reused_existing=reused,
        message=job.message,
    )


@router.get("/coverage/jobs/{job_id}", response_model=AnalysisJobResponse)
def coverage_job_status(
    job_id: str,
    jobs: CoverageJobManager = Depends(coverage_job_manager),
) -> AnalysisJobResponse:
    return _job_response(jobs.get(job_id))


@router.get("/{video_id}/coverage", response_model=CoverageResultResponse)
def coverage_result(
    video_id: str,
    coverage: CoverageService = Depends(coverage_service),
) -> CoverageResultResponse:
    validate_video_id(video_id)
    result = coverage.get_result(video_id)
    if not result:
        raise AppError(ErrorCode.COVERAGE_NOT_FOUND, "A valid lecture coverage audit has not been generated yet.", 404)
    return CoverageResultResponse.model_validate(result)
