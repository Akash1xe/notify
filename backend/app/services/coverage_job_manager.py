from __future__ import annotations

import logging
import threading
import uuid

from app.core.errors import AppError, ErrorCode
from app.models.job import JobRecord, JobStatus, JobType, utc_now_iso
from app.services.coverage_service import CoverageService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class CoverageJobManager:
    def __init__(self, storage: StorageService, coverage: CoverageService) -> None:
        self.storage = storage
        self.coverage = coverage
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
            job_type=JobType.COVERAGE_AUDIT,
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

    def start(self, video_id: str) -> tuple[JobRecord, bool]:
        existing = self.coverage.get_result(video_id)
        if existing:
            passed = bool((existing.get("summary") or {}).get("coverage_passed"))
            message = "Coverage audit already exists and is valid."
            if not passed:
                message = "Coverage audit already exists and still contains blocking findings."
            job = self._new_job(video_id, JobStatus.READY, 100.0, message)
            with self._lock:
                self._jobs[job.job_id] = job
            return job, True

        with self._lock:
            active_id = self._active_by_video.get(video_id)
            if active_id:
                active = self._jobs.get(active_id)
                if active and active.status.transient:
                    return active, False
            job = self._new_job(video_id, JobStatus.QUEUED, 0.0, "Queued for lecture coverage verification...")
            self._jobs[job.job_id] = job
            self._active_by_video[video_id] = job.job_id
            self._persist(job)

        threading.Thread(target=self._run, args=(job.job_id,), name=f"coverage-{video_id}", daemon=True).start()
        return job, False

    def _run(self, job_id: str) -> None:
        job = self._jobs[job_id]
        try:
            self._update(job_id, JobStatus.VERIFYING_COVERAGE, 1.0, "Starting fail-closed coverage audit...")
            result = self.coverage.process(
                job.video_id,
                lambda progress, message: self._update(job_id, JobStatus.VERIFYING_COVERAGE, progress, message),
            )
            summary = result.get("summary") or {}
            if bool(summary.get("coverage_passed")):
                message = "Lecture coverage passed. The trusted screenshot set is ready for PDF generation."
            else:
                message = f"Coverage audit found {int(summary.get('blocking_finding_count') or 0)} blocking finding(s)."
            self._update(job_id, JobStatus.READY, 100.0, message)
            self.storage.cleanup_job_workspace(job_id)
        except AppError as exc:
            logger.warning("Coverage audit failed for job %s: %s", job_id, exc.code)
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
            logger.exception("Unexpected coverage audit failure for job %s", job_id)
            with self._lock:
                current = self._jobs[job_id]
                current.status = JobStatus.FAILED
                current.message = "Lecture coverage verification failed unexpectedly."
                current.error_code = ErrorCode.INTERNAL_ERROR
                current.error_message = "Lecture coverage verification failed unexpectedly."
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
        if persisted and persisted.job_type == JobType.COVERAGE_AUDIT:
            return persisted
        raise AppError(ErrorCode.JOB_NOT_FOUND, "The requested coverage-audit job was not found.", 404)
