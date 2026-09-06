from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api.dependencies import pdf_generation_job_manager, pdf_service
from app.core.errors import AppError, ErrorCode
from app.schemas.analysis import AnalysisJobError, AnalysisJobResponse
from app.schemas.pdf import (
    PdfResultResponse,
    PdfReviewResponse,
    StartPdfGenerationRequest,
    StartPdfGenerationResponse,
    UpdatePdfReviewRequest,
)
from app.services.pdf_job_manager import PdfGenerationJobManager
from app.services.pdf_service import PdfService
from app.utils.youtube_url import validate_video_id

router = APIRouter(prefix="/api/pdf", tags=["pdf"])


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


@router.post("/start", response_model=StartPdfGenerationResponse)
def start_pdf_generation(
    payload: StartPdfGenerationRequest,
    jobs: PdfGenerationJobManager = Depends(pdf_generation_job_manager),
) -> StartPdfGenerationResponse:
    validate_video_id(payload.video_id)
    job, reused = jobs.start(payload.video_id, payload.settings.model_dump())
    return StartPdfGenerationResponse(
        job_id=job.job_id,
        video_id=job.video_id,
        status=job.status,
        reused_existing=reused,
        message=job.message,
    )


@router.get("/jobs/{job_id}", response_model=AnalysisJobResponse)
def pdf_job_status(
    job_id: str,
    jobs: PdfGenerationJobManager = Depends(pdf_generation_job_manager),
) -> AnalysisJobResponse:
    return _job_response(jobs.get(job_id))


@router.get("/{video_id}/review", response_model=PdfReviewResponse)
def pdf_review(video_id: str, pdf: PdfService = Depends(pdf_service)) -> PdfReviewResponse:
    validate_video_id(video_id)
    return PdfReviewResponse.model_validate(pdf.get_review(video_id))


@router.put("/{video_id}/review", response_model=PdfReviewResponse)
def update_pdf_review(
    video_id: str,
    payload: UpdatePdfReviewRequest,
    pdf: PdfService = Depends(pdf_service),
) -> PdfReviewResponse:
    validate_video_id(video_id)
    return PdfReviewResponse.model_validate(pdf.update_review(video_id, payload.ordered_trusted_indexes))


@router.get("/{video_id}", response_model=PdfResultResponse)
def pdf_result(video_id: str, pdf: PdfService = Depends(pdf_service)) -> PdfResultResponse:
    validate_video_id(video_id)
    result = pdf.get_result(video_id)
    if not result:
        raise AppError(ErrorCode.PDF_NOT_FOUND, "A current coverage-verified PDF has not been generated yet.", 404)
    return PdfResultResponse(pdf=result)


@router.get("/{video_id}/preview")
def preview_pdf(video_id: str, pdf: PdfService = Depends(pdf_service)) -> FileResponse:
    validate_video_id(video_id)
    path, result = pdf.download_path(video_id)
    filename = str(result.get("file_name") or "lecture-notes.pdf").replace('"', "")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


@router.get("/{video_id}/download")
def download_pdf(video_id: str, pdf: PdfService = Depends(pdf_service)) -> FileResponse:
    validate_video_id(video_id)
    path, result = pdf.download_path(video_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=str(result.get("file_name") or "lecture-notes.pdf"),
        headers={"Cache-Control": "no-store"},
    )
