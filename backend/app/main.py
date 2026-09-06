from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.services.candidate_review_service import CandidateReviewService
from app.services.coverage_job_manager import CoverageJobManager
from app.services.coverage_service import CoverageService
from app.services.frame_analysis_job_manager import FrameAnalysisJobManager
from app.services.frame_timeline_service import FrameTimelineService
from app.services.job_manager import JobManager
from app.services.media_service import MediaService
from app.services.ocr_job_manager import OcrJobManager
from app.services.ocr_service import OcrService
from app.services.pdf_job_manager import PdfGenerationJobManager
from app.services.pdf_service import PdfService
from app.services.prepared_video_service import PreparedVideoService
from app.services.screenshot_candidate_job_manager import ScreenshotCandidateJobManager
from app.services.screenshot_candidate_service import ScreenshotCandidateService
from app.services.storage_service import StorageService
from app.services.teaching_state_job_manager import TeachingStateJobManager
from app.services.teaching_state_service import TeachingStateService
from app.services.topic_detection_job_manager import TopicDetectionJobManager
from app.services.topic_detection_service import TopicDetectionService
from app.services.transcription_job_manager import TranscriptionJobManager
from app.services.transcription_service import TranscriptionService
from app.services.video_download_service import VideoDownloadService
from app.services.visual_change_job_manager import VisualChangeJobManager
from app.services.visual_change_service import VisualChangeService
from app.services.youtube_service import YoutubeService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = StorageService(
        downloads_dir=settings.downloads_dir,
        temp_dir=settings.temp_dir,
        output_dir=settings.output_dir,
        temp_retention_hours=settings.temp_retention_hours,
    )
    storage.initialize()
    recovered = storage.recover_interrupted_jobs()

    media = MediaService()
    youtube = YoutubeService()
    prepared = PreparedVideoService(storage, media)
    downloader = VideoDownloadService(
        storage=storage,
        media=media,
        max_video_height=settings.max_video_height,
        min_free_space_bytes=settings.min_free_space_bytes,
    )
    jobs = JobManager(storage=storage, youtube=youtube, downloader=downloader, prepared=prepared)

    # Visual stages are adaptive: source metadata only, coarse whole-video scan,
    # fine activity-window scan, then teaching checkpoints and direct screenshot seeks.
    frame_timeline = FrameTimelineService(storage=storage, prepared=prepared)
    analysis_jobs = FrameAnalysisJobManager(storage=storage, timeline=frame_timeline)
    visual_changes = VisualChangeService(storage=storage, prepared=prepared, timeline=frame_timeline)
    teaching_states = TeachingStateService(storage=storage, prepared=prepared, timeline=frame_timeline, changes=visual_changes)
    teaching_state_jobs = TeachingStateJobManager(storage=storage, states=teaching_states)
    screenshot_candidates = ScreenshotCandidateService(storage=storage, prepared=prepared, states=teaching_states)
    screenshot_candidate_jobs = ScreenshotCandidateJobManager(storage=storage, candidates=screenshot_candidates)
    candidate_review = CandidateReviewService(storage=storage, prepared=prepared, candidates=screenshot_candidates)

    # Raw Whisper transcription is source-video cached and can be prewarmed while
    # adaptive visual scanning runs. Screenshot alignment remains dependent on the
    # trusted screenshot set and is rebuilt later when required.
    transcription = TranscriptionService(
        storage=storage,
        prepared=prepared,
        media=media,
        review=candidate_review,
        model_name=settings.whisper_model,
        language=settings.whisper_language,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    visual_change_jobs = VisualChangeJobManager(storage=storage, changes=visual_changes, transcription=transcription)
    transcription_jobs = TranscriptionJobManager(storage=storage, transcription=transcription)

    topic_detection = TopicDetectionService(storage=storage, transcription=transcription, review=candidate_review)
    topic_detection_jobs = TopicDetectionJobManager(storage=storage, topics=topic_detection)
    ocr = OcrService(
        storage=storage,
        review=candidate_review,
        topics=topic_detection,
        tesseract_cmd=settings.tesseract_cmd,
        language=settings.ocr_language,
        psm=settings.ocr_psm,
    )
    ocr_jobs = OcrJobManager(storage=storage, ocr=ocr)
    coverage = CoverageService(
        storage=storage,
        review=candidate_review,
        topics=topic_detection,
        ocr=ocr,
        visual_changes=visual_changes,
    )
    coverage_jobs = CoverageJobManager(storage=storage, coverage=coverage)
    pdf = PdfService(storage=storage, coverage=coverage, review=candidate_review, topics=topic_detection)
    pdf_jobs = PdfGenerationJobManager(storage=storage, pdf=pdf)

    app.state.storage = storage
    app.state.media = media
    app.state.youtube = youtube
    app.state.prepared = prepared
    app.state.downloader = downloader
    app.state.jobs = jobs
    app.state.frame_timeline = frame_timeline
    app.state.analysis_jobs = analysis_jobs
    app.state.visual_changes = visual_changes
    app.state.visual_change_jobs = visual_change_jobs
    app.state.teaching_states = teaching_states
    app.state.teaching_state_jobs = teaching_state_jobs
    app.state.screenshot_candidates = screenshot_candidates
    app.state.screenshot_candidate_jobs = screenshot_candidate_jobs
    app.state.candidate_review = candidate_review
    app.state.transcription = transcription
    app.state.transcription_jobs = transcription_jobs
    app.state.topic_detection = topic_detection
    app.state.topic_detection_jobs = topic_detection_jobs
    app.state.ocr = ocr
    app.state.ocr_jobs = ocr_jobs
    app.state.coverage = coverage
    app.state.coverage_jobs = coverage_jobs
    app.state.pdf = pdf
    app.state.pdf_jobs = pdf_jobs

    logger.info(
        "Notify backend ready. ffmpeg=%s ffprobe=%s whisper_model=%s tesseract=%s adaptive=%sfps/%sfps recovered_jobs=%s",
        bool(media.ffmpeg_path),
        bool(media.ffprobe_path),
        settings.whisper_model,
        ocr.available,
        settings.analysis_coarse_fps,
        settings.analysis_fine_fps,
        recovered,
    )
    yield


app = FastAPI(title="Notify Local Processing Service", version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error", exc_info=exc)
    return JSONResponse(status_code=500, content={"error": {"code": ErrorCode.INTERNAL_ERROR, "message": "The local processing service encountered an unexpected error."}})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "lecture-to-pdf-backend"}
