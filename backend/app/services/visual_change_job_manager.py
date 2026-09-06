from __future__ import annotations

import logging
import threading
import uuid

from app.core.errors import AppError, ErrorCode
from app.models.job import JobRecord, JobStatus, JobType, utc_now_iso
from app.services.storage_service import StorageService
from app.services.transcription_service import TranscriptionService
from app.services.visual_change_service import VisualChangeService

logger = logging.getLogger(__name__)


class VisualChangeJobManager:
    def __init__(self, storage: StorageService, changes: VisualChangeService, transcription: TranscriptionService | None = None) -> None:
        self.storage = storage
        self.changes = changes
        self.transcription = transcription
        self._jobs: dict[str, JobRecord] = {}
        self._active_by_video: dict[str, str] = {}
        self._transcript_prewarm_active: set[str] = set()
        self._lock = threading.RLock()

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
            job_type=JobType.VISUAL_CHANGE,
        )

    def _persist(self, job: JobRecord) -> None:
        self.storage.create_job_workspace(job.job_id)
        self.storage.write_job(job)

    def _update(self, job_id: str, status: JobStatus, progress: float, message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = status
            job.progress = min(100.0, max(0.0, progress))
            job.message = message
            job.updated_at = utc_now_iso()
            self._persist(job)

    def _start_transcript_prewarm(self, video_id: str) -> None:
        if self.transcription is None:
            return
        with self._lock:
            if video_id in self._transcript_prewarm_active:
                return
            # Raw transcript validity intentionally does not depend on trusted screenshots.
            if self.transcription._valid_transcript_summary(video_id) is not None:
                return
            self._transcript_prewarm_active.add(video_id)

        def run() -> None:
            try:
                logger.info("Prewarming raw transcript while adaptive visual analysis runs for %s", video_id)
                self.transcription._transcribe(video_id, lambda _stage, _progress, _message: None)
            except AppError as exc:
                # Visual analysis remains independent. The normal transcript job can retry
                # and surface the error later if model/audio setup is unavailable.
                logger.warning("Transcript prewarm skipped/failed for %s: %s", video_id, exc.code)
            except Exception:
                logger.exception("Transcript prewarm failed unexpectedly for %s", video_id)
            finally:
                with self._lock:
                    self._transcript_prewarm_active.discard(video_id)

        threading.Thread(target=run, name=f"transcript-prewarm-{video_id}", daemon=True).start()

    def start(self, video_id: str) -> tuple[JobRecord, bool]:
        existing = self.changes.get_summary(video_id)
        if existing:
            job = self._new_job(video_id, JobStatus.READY, 100.0, "Adaptive visual analysis already exists and is valid.")
            with self._lock:
                self._jobs[job.job_id] = job
            self._start_transcript_prewarm(video_id)
            return job, True

        with self._lock:
            active_id = self._active_by_video.get(video_id)
            if active_id:
                active = self._jobs.get(active_id)
                if active and active.status.transient:
                    return active, False

            job = self._new_job(video_id, JobStatus.QUEUED, 0.0, "Queued for adaptive visual analysis...")
            self._jobs[job.job_id] = job
            self._active_by_video[video_id] = job.job_id
            self._persist(job)

        self._start_transcript_prewarm(video_id)
        threading.Thread(target=self._run, args=(job.job_id,), name=f"changes-{video_id}", daemon=True).start()
        return job, False

    def _run(self, job_id: str) -> None:
        job = self._jobs[job_id]
        try:
            self._update(job_id, JobStatus.COMPARING_FRAMES, 0.0, "Starting coarse adaptive scan...")
            self.changes.scan(
                job.video_id,
                lambda progress, message: self._update(job_id, JobStatus.COMPARING_FRAMES, progress, message),
            )
            self._update(job_id, JobStatus.READY, 100.0, "Adaptive visual scan ready.")
            self.storage.cleanup_job_workspace(job_id)
        except AppError as exc:
            logger.warning("Adaptive visual analysis failed for job %s: %s", job_id, exc.code)
            with self._lock:
                current = self._jobs[job_id]
                current.status = JobStatus.FAILED
                current.message = exc.message
                current.error_code = exc.code
                current.error_message = exc.message
                current.updated_at = utc_now_iso()
                self._persist(current)
            self.storage.cleanup_failed_job_media(job_id)
        except Exception:
            logger.exception("Unexpected adaptive visual analysis failure for job %s", job_id)
            with self._lock:
                current = self._jobs[job_id]
                current.status = JobStatus.FAILED
                current.message = "Adaptive visual analysis failed unexpectedly."
                current.error_code = ErrorCode.INTERNAL_ERROR
                current.error_message = "Adaptive visual analysis failed unexpectedly."
                current.updated_at = utc_now_iso()
                self._persist(current)
        finally:
            with self._lock:
                if self._active_by_video.get(job.video_id) == job_id:
                    self._active_by_video.pop(job.video_id, None)

    def get(self, job_id: str) -> JobRecord:
        self.storage.validate_job_id(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
        if job:
            return job
        persisted = self.storage.read_job(job_id)
        if persisted and persisted.job_type == JobType.VISUAL_CHANGE:
            return persisted
        raise AppError(ErrorCode.JOB_NOT_FOUND, "The requested adaptive visual analysis job was not found.", 404)
