from __future__ import annotations

import logging
import threading
import uuid
from typing import Callable

from app.core.errors import AppError, ErrorCode
from app.models.job import JobRecord, JobStatus, utc_now_iso
from app.schemas.video import PrepareResponse
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService
from app.services.video_download_service import VideoDownloadService
from app.services.youtube_service import YoutubeService
from app.utils.youtube_url import normalize_youtube_url

logger = logging.getLogger(__name__)


class JobManager:
    def __init__(
        self,
        storage: StorageService,
        youtube: YoutubeService,
        downloader: VideoDownloadService,
        prepared: PreparedVideoService,
    ) -> None:
        self.storage = storage
        self.youtube = youtube
        self.downloader = downloader
        self.prepared = prepared
        self._jobs: dict[str, JobRecord] = {}
        self._active_by_video: dict[str, str] = {}
        self._lock = threading.RLock()

    def active_job_ids(self) -> list[str]:
        with self._lock:
            return [job_id for job_id, job in self._jobs.items() if job.status.transient]

    def _new_job(self, video_id: str, status: JobStatus, progress: float, message: str) -> JobRecord:
        now = utc_now_iso()
        return JobRecord(
            job_id=f"job_{uuid.uuid4().hex}",
            video_id=video_id,
            status=status,
            progress=progress,
            message=message,
            created_at=now,
            updated_at=now,
        )

    def _persist(self, job: JobRecord) -> None:
        try:
            self.storage.create_job_workspace(job.job_id)
            self.storage.write_job(job)
        except AppError:
            logger.exception("Could not persist job %s", job.job_id)

    def _update(self, job_id: str, status: JobStatus, progress: float, message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            job.progress = min(100.0, max(0.0, progress))
            job.message = message
            job.updated_at = utc_now_iso()
            self._persist(job)

    def start_prepare(self, url: str, requested_video_id: str) -> PrepareResponse:
        parsed_video_id, normalized_url = normalize_youtube_url(url)
        if parsed_video_id != requested_video_id:
            raise AppError(ErrorCode.INVALID_YOUTUBE_URL, "The submitted YouTube URL does not match the video ID.", 400)

        existing = self.prepared.get_prepared_video(requested_video_id)
        if existing:
            job = self._new_job(requested_video_id, JobStatus.READY, 100.0, "Video ready for analysis.")
            with self._lock:
                self._jobs[job.job_id] = job
            return PrepareResponse(
                job_id=job.job_id,
                video_id=requested_video_id,
                status=JobStatus.READY,
                reused_existing=True,
                message="Existing prepared video found and verified.",
            )

        with self._lock:
            active_id = self._active_by_video.get(requested_video_id)
            if active_id:
                active = self._jobs.get(active_id)
                if active and active.status.transient:
                    return PrepareResponse(
                        job_id=active.job_id,
                        video_id=active.video_id,
                        status=active.status,
                        reused_existing=False,
                        message="An existing preparation job is already running for this video.",
                    )

            job = self._new_job(requested_video_id, JobStatus.QUEUED, 0.0, "Queued for local preparation...")
            self._jobs[job.job_id] = job
            self._active_by_video[requested_video_id] = job.job_id
            self._persist(job)

        thread = threading.Thread(
            target=self._run_prepare,
            args=(job.job_id, normalized_url),
            name=f"prepare-{requested_video_id}",
            daemon=True,
        )
        thread.start()
        return PrepareResponse(
            job_id=job.job_id,
            video_id=job.video_id,
            status=job.status,
            reused_existing=False,
            message=job.message,
        )

    def _run_prepare(self, job_id: str, normalized_url: str) -> None:
        job = self._jobs[job_id]
        try:
            # Re-inspect on the backend before touching the filesystem. Frontend state is
            # never treated as an authorization or source of truth.
            metadata = self.youtube.metadata(normalized_url)
            if metadata.video_id != job.video_id:
                raise AppError(ErrorCode.INVALID_YOUTUBE_URL, "The submitted YouTube video changed during preparation.", 400)

            callback: Callable[[JobStatus, float, str], None] = lambda status, progress, message: self._update(
                job_id, status, progress, message
            )
            self.downloader.prepare(job_id, metadata, callback)
            self._update(job_id, JobStatus.READY, 100.0, "Video ready for analysis.")
            # Polling uses the in-memory READY record. Runtime temp media can now be removed.
            self.storage.cleanup_job_workspace(job_id)
        except AppError as exc:
            logger.warning("Preparation failed for job %s: %s", job_id, exc.code)
            with self._lock:
                job = self._jobs[job_id]
                job.status = JobStatus.FAILED
                job.progress = min(job.progress, 99.0)
                job.message = exc.message
                job.error_code = exc.code
                job.error_message = exc.message
                job.updated_at = utc_now_iso()
                self._persist(job)
            self.storage.cleanup_failed_job_media(job_id)
        except Exception:
            logger.exception("Unexpected preparation failure for job %s", job_id)
            with self._lock:
                job = self._jobs[job_id]
                job.status = JobStatus.FAILED
                job.message = "Video preparation failed unexpectedly."
                job.error_code = ErrorCode.INTERNAL_ERROR
                job.error_message = "Video preparation failed unexpectedly."
                job.updated_at = utc_now_iso()
                self._persist(job)
            self.storage.cleanup_failed_job_media(job_id)
        finally:
            with self._lock:
                current = self._active_by_video.get(job.video_id)
                if current == job_id:
                    self._active_by_video.pop(job.video_id, None)

    def get(self, job_id: str) -> JobRecord:
        self.storage.validate_job_id(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
        if job:
            return job
        persisted = self.storage.read_job(job_id)
        if persisted:
            return persisted
        raise AppError(ErrorCode.JOB_NOT_FOUND, "The requested processing job was not found.", 404)
