from fastapi import Request

from app.services.frame_analysis_job_manager import FrameAnalysisJobManager
from app.services.frame_timeline_service import FrameTimelineService
from app.services.job_manager import JobManager
from app.services.media_service import MediaService
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService
from app.services.visual_change_job_manager import VisualChangeJobManager
from app.services.visual_change_service import VisualChangeService
from app.services.youtube_service import YoutubeService


def storage_service(request: Request) -> StorageService:
    return request.app.state.storage


def media_service(request: Request) -> MediaService:
    return request.app.state.media


def youtube_service(request: Request) -> YoutubeService:
    return request.app.state.youtube


def prepared_video_service(request: Request) -> PreparedVideoService:
    return request.app.state.prepared


def job_manager(request: Request) -> JobManager:
    return request.app.state.jobs


def frame_timeline_service(request: Request) -> FrameTimelineService:
    return request.app.state.frame_timeline


def frame_analysis_job_manager(request: Request) -> FrameAnalysisJobManager:
    return request.app.state.analysis_jobs


def visual_change_service(request: Request) -> VisualChangeService:
    return request.app.state.visual_changes


def visual_change_job_manager(request: Request) -> VisualChangeJobManager:
    return request.app.state.visual_change_jobs
