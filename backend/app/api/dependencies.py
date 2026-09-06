from fastapi import Request

from app.services.candidate_review_service import CandidateReviewService
from app.services.frame_analysis_job_manager import FrameAnalysisJobManager
from app.services.frame_timeline_service import FrameTimelineService
from app.services.job_manager import JobManager
from app.services.media_service import MediaService
from app.services.ocr_job_manager import OcrJobManager
from app.services.ocr_service import OcrService
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


def teaching_state_service(request: Request) -> TeachingStateService:
    return request.app.state.teaching_states


def teaching_state_job_manager(request: Request) -> TeachingStateJobManager:
    return request.app.state.teaching_state_jobs


def screenshot_candidate_service(request: Request) -> ScreenshotCandidateService:
    return request.app.state.screenshot_candidates


def screenshot_candidate_job_manager(request: Request) -> ScreenshotCandidateJobManager:
    return request.app.state.screenshot_candidate_jobs


def candidate_review_service(request: Request) -> CandidateReviewService:
    return request.app.state.candidate_review


def transcription_service(request: Request) -> TranscriptionService:
    return request.app.state.transcription


def transcription_job_manager(request: Request) -> TranscriptionJobManager:
    return request.app.state.transcription_jobs


def topic_detection_service(request: Request) -> TopicDetectionService:
    return request.app.state.topic_detection


def topic_detection_job_manager(request: Request) -> TopicDetectionJobManager:
    return request.app.state.topic_detection_jobs


def ocr_service(request: Request) -> OcrService:
    return request.app.state.ocr


def ocr_job_manager(request: Request) -> OcrJobManager:
    return request.app.state.ocr_jobs
