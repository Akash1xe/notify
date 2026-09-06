from __future__ import annotations

import logging
import threading
import uuid

from app.core.errors import AppError, ErrorCode
from app.models.job import JobRecord, JobStatus, JobType, utc_now_iso
from app.services.storage_service import StorageService
from app.services.transcription_service import TranscriptionService

logger = logging.getLogger(__name__)


class TranscriptionJobManager:
    def __init__(self, storage: StorageService, transcription: TranscriptionService) -> None:
        self.storage = storage
        self.transcription = transcription
        self._jobs: dict[str, JobRecord] = {}
        self._active_by_video: dict[str, str] = {}
        self._lock = threading.RLock()
        if not hasattr(self.transcription, "_raw_process_lock"):
            setattr(self.transcription, "_raw_process_lock", threading.RLock())

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
            job_type=JobType.TRANSCRIPTION,
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

    @staticmethod
    def _status_for_stage(stage: str) -> JobStatus:
        if stage == "AUDIO":
            return JobStatus.EXTRACTING_AUDIO
        if stage == "ALIGN":
            return JobStatus.ALIGNING_TRANSCRIPT
        return JobStatus.TRANSCRIBING

    def start(self, video_id: str) -> tuple[JobRecord, bool]:
        existing = self.transcription.get_result(video_id)
        if existing:
            job = self._new_job(video_id, JobStatus.READY, 100.0, "Transcript and screenshot alignment already exist and are valid.")
            with self._lock:
                self._jobs[job.job_id] = job
            return job, True

        with self._lock:
            active_id = self._active_by_video.get(video_id)
            if active_id:
                active = self._jobs.get(active_id)
                if active and active.status.transient:
                    return active, False

            job = self._new_job(video_id, JobStatus.QUEUED, 0.0, "Queued for local transcript generation...")
            self._jobs[job.job_id] = job
            self._active_by_video[video_id] = job.job_id
            self._persist(job)

        threading.Thread(target=self._run, args=(job.job_id,), name=f"transcript-{video_id}", daemon=True).start()
        return job, False

    def _run(self, job_id: str) -> None:
        job = self._jobs[job_id]
        try:
            process_lock = getattr(self.transcription, "_raw_process_lock")
            self._update(job_id, JobStatus.TRANSCRIBING, 0.0, "Waiting for/reusing any transcript prewarm already in progress...")
            with process_lock:
                self.transcription.process(
                    job.video_id,
                    lambda stage, progress, message: self._update(
                        job_id,
                        self._status_for_stage(stage),
                        progress,
                        message,
                    ),
                )
            self._update(job_id, JobStatus.READY, 100.0, "Timestamped transcript and screenshot alignment are ready.")
            self.storage.cleanup_job_workspace(job_id)
        except AppError as exc:
            logger.warning("Transcription failed for job %s: %s", job_id, exc.code)
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
            logger.exception("Unexpected transcription failure for job %s", job_id)
            with self._lock:
                current = self._jobs[job_id]
                current.status = JobStatus.FAILED
                current.message = "Transcript generation failed unexpectedly."
                current.error_code = ErrorCode.INTERNAL_ERROR
                current.error_message = "Transcript generation failed unexpectedly."
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
        if persisted and persisted.job_type == JobType.TRANSCRIPTION:
            return persisted
        raise AppError(ErrorCode.JOB_NOT_FOUND, "The requested transcription job was not found.", 404)
