from __future__ import annotations

import logging
import threading
import uuid

from app.core.errors import AppError, ErrorCode
from app.models.job import JobRecord, JobStatus, JobType, utc_now_iso
from app.services.pdf_service import PdfService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class PdfGenerationJobManager:
    def __init__(self, storage: StorageService, pdf: PdfService) -> None:
        self.storage = storage
        self.pdf = pdf
        self._jobs: dict[str, JobRecord] = {}
        self._active_by_video: dict[str, str] = {}
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
            job_type=JobType.PDF_GENERATION,
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

    def start(self, video_id: str, settings: dict | None = None) -> tuple[JobRecord, bool]:
        normalized = self.pdf.normalize_settings(settings)
        if self.pdf.matches_settings(video_id, normalized):
            job = self._new_job(video_id, JobStatus.READY, 100.0, "A current PDF with these settings already exists.")
            with self._lock:
                self._jobs[job.job_id] = job
            return job, True

        with self._lock:
            active_id = self._active_by_video.get(video_id)
            if active_id:
                active = self._jobs.get(active_id)
                if active and active.status.transient:
                    return active, False
            job = self._new_job(video_id, JobStatus.QUEUED, 0.0, "Queued for final PDF generation...")
            self._jobs[job.job_id] = job
            self._active_by_video[video_id] = job.job_id
            self._persist(job)

        threading.Thread(
            target=self._run,
            args=(job.job_id, normalized),
            name=f"pdf-{video_id}",
            daemon=True,
        ).start()
        return job, False

    def _run(self, job_id: str, settings: dict) -> None:
        job = self._jobs[job_id]
        try:
            self._update(job_id, JobStatus.GENERATING_PDF, 1.0, "Starting final PDF generation...")
            result = self.pdf.generate(
                job.video_id,
                settings,
                lambda progress, message: self._update(job_id, JobStatus.GENERATING_PDF, progress, message),
            )
            self._update(
                job_id,
                JobStatus.READY,
                100.0,
                f"PDF ready: {int(result.get('page_count') or 0)} page(s).",
            )
            self.storage.cleanup_job_workspace(job_id)
        except AppError as exc:
            logger.warning("PDF generation failed for job %s: %s", job_id, exc.code)
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
            logger.exception("Unexpected PDF generation failure for job %s", job_id)
            with self._lock:
                current = self._jobs[job_id]
                current.status = JobStatus.FAILED
                current.message = "Final PDF generation failed unexpectedly."
                current.error_code = ErrorCode.INTERNAL_ERROR
                current.error_message = "Final PDF generation failed unexpectedly."
                current.updated_at = utc_now_iso()
                self._persist(current)
        finally:
            with self._lock:
                if self._active_by_video.get(job.video_id) == job_id:
                    self._active_by_video.pop(job.video_id, None)

    def _normalize_recovered_job(self, job: JobRecord) -> JobRecord:
        # Storage recovery is shared with video preparation. Older/generic recovery
        # may mark an interrupted PDF job with PREPARATION_INTERRUPTED; correct the
        # persisted message the first time this job is read after restart.
        if (
            job.job_type == JobType.PDF_GENERATION
            and job.status == JobStatus.INTERRUPTED
            and job.error_code == ErrorCode.PREPARATION_INTERRUPTED
        ):
            job.message = "PDF generation was interrupted before completion."
            job.error_code = ErrorCode.ANALYSIS_INTERRUPTED
            job.error_message = "PDF generation was interrupted. Generate the PDF again."
            job.updated_at = utc_now_iso()
            self.storage.write_job(job)
        return job

    def get(self, job_id: str) -> JobRecord:
        self.storage.validate_job_id(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
        if job:
            return job
        persisted = self.storage.read_job(job_id)
        if persisted and persisted.job_type == JobType.PDF_GENERATION:
            return self._normalize_recovered_job(persisted)
        raise AppError(ErrorCode.JOB_NOT_FOUND, "The requested PDF-generation job was not found.", 404)
