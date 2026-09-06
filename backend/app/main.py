from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.services.frame_analysis_job_manager import FrameAnalysisJobManager
from app.services.frame_timeline_service import FrameTimelineService
from app.services.job_manager import JobManager
from app.services.media_service import MediaService
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService
from app.services.video_download_service import VideoDownloadService
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
    frame_timeline = FrameTimelineService(storage=storage, prepared=prepared)
    analysis_jobs = FrameAnalysisJobManager(storage=storage, timeline=frame_timeline)

    app.state.storage = storage
    app.state.media = media
    app.state.youtube = youtube
    app.state.prepared = prepared
    app.state.downloader = downloader
    app.state.jobs = jobs
    app.state.frame_timeline = frame_timeline
    app.state.analysis_jobs = analysis_jobs

    logger.info(
        "Notify backend ready. ffmpeg=%s ffprobe=%s recovered_jobs=%s",
        bool(media.ffmpeg_path), bool(media.ffprobe_path), recovered,
    )
    yield


app = FastAPI(title="Notify Local Processing Service", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": ErrorCode.INTERNAL_ERROR, "message": "The local processing service encountered an unexpected error."}},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "lecture-to-pdf-backend"}
