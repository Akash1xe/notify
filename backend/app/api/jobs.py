from fastapi import APIRouter, Depends

from app.api.dependencies import job_manager
from app.schemas.jobs import JobErrorResponse, JobResponse
from app.services.job_manager import JobManager

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, jobs: JobManager = Depends(job_manager)) -> JobResponse:
    job = jobs.get(job_id)
    error = None
    if job.error_code and job.error_message:
        error = JobErrorResponse(code=job.error_code, message=job.error_message)
    return JobResponse(
        job_id=job.job_id,
        video_id=job.video_id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        error=error,
    )
