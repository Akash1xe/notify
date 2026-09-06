from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from app.core.errors import AppError, ErrorCode
from app.models.job import JobRecord, JobStatus, utc_now_iso
from app.utils.youtube_url import validate_video_id

logger = logging.getLogger(__name__)
JOB_ID_RE = re.compile(r"^job_[a-f0-9]{32}$")


class StorageService:
    def __init__(self, downloads_dir: Path, temp_dir: Path, output_dir: Path, temp_retention_hours: int = 24) -> None:
        self.downloads_dir = downloads_dir.resolve()
        self.temp_dir = temp_dir.resolve()
        self.output_dir = output_dir.resolve()
        self.temp_retention_hours = temp_retention_hours

    def initialize(self) -> None:
        for directory in (self.downloads_dir, self.temp_dir, self.output_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def _assert_within(self, path: Path, root: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise AppError(ErrorCode.STORAGE_ERROR, "An unsafe local storage path was rejected.", 400) from exc
        return resolved

    def validate_job_id(self, job_id: str) -> str:
        if not JOB_ID_RE.fullmatch(job_id):
            raise AppError(ErrorCode.JOB_NOT_FOUND, "The requested processing job was not found.", 404)
        return job_id

    def video_dir(self, video_id: str) -> Path:
        validate_video_id(video_id)
        return self._assert_within(self.downloads_dir / video_id, self.downloads_dir)

    def prepared_video_path(self, video_id: str) -> Path:
        return self.video_dir(video_id) / "lecture.mp4"

    def video_manifest_path(self, video_id: str) -> Path:
        return self.video_dir(video_id) / "metadata.json"

    def job_dir(self, job_id: str) -> Path:
        self.validate_job_id(job_id)
        return self._assert_within(self.temp_dir / job_id, self.temp_dir)

    def job_manifest_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def create_job_workspace(self, job_id: str) -> Path:
        root = self.job_dir(job_id)
        (root / "source").mkdir(parents=True, exist_ok=True)
        (root / "processing").mkdir(parents=True, exist_ok=True)
        return root

    def _atomic_json_write(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.STORAGE_ERROR, "Local storage could not be updated.", 500) from exc

    def write_job(self, job: JobRecord) -> None:
        self._atomic_json_write(self.job_manifest_path(job.job_id), job.to_dict())

    def read_job(self, job_id: str) -> JobRecord | None:
        path = self.job_manifest_path(job_id)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                return None
            return JobRecord.from_dict(payload)
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return None

    def write_video_manifest(self, video_id: str, metadata: dict[str, Any]) -> None:
        validate_video_id(video_id)
        payload = dict(metadata)
        payload["video_id"] = video_id
        payload["local_filename"] = "lecture.mp4"
        payload["status"] = "READY"
        payload.setdefault("prepared_at", utc_now_iso())
        self._atomic_json_write(self.video_manifest_path(video_id), payload)

    def read_video_manifest(self, video_id: str) -> dict[str, Any] | None:
        path = self.video_manifest_path(video_id)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict) or payload.get("video_id") != video_id or payload.get("status") != "READY":
                return None
            return payload
        except (OSError, json.JSONDecodeError):
            return None

    def finalize_video(self, job_id: str, video_id: str, source: Path, metadata: dict[str, Any]) -> Path:
        source = self._assert_within(source, self.job_dir(job_id))
        final_dir = self.video_dir(video_id)
        final_dir.mkdir(parents=True, exist_ok=True)
        final_path = self.prepared_video_path(video_id)
        staging_path = final_dir / "lecture.mp4.tmp"

        if not source.exists():
            raise AppError(ErrorCode.STORAGE_ERROR, "Prepared media was not found during finalization.", 500)

        try:
            staging_path.unlink(missing_ok=True)
            shutil.move(str(source), str(staging_path))
            os.replace(staging_path, final_path)
            self.write_video_manifest(video_id, metadata)
        except OSError as exc:
            staging_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.STORAGE_ERROR, "The prepared video could not be finalized locally.", 500) from exc

        logger.info("Finalized prepared video %s", video_id)
        return final_path

    def delete_prepared_video(self, video_id: str) -> bool:
        directory = self.video_dir(video_id)
        if not directory.exists():
            return False
        shutil.rmtree(directory)
        logger.info("Deleted prepared video %s", video_id)
        return True

    def cleanup_job_workspace(self, job_id: str) -> None:
        root = self.job_dir(job_id)
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)

    def cleanup_failed_job_media(self, job_id: str) -> None:
        root = self.job_dir(job_id)
        if not root.exists():
            return
        for child in root.iterdir():
            if child.name == "job.json":
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)

    def recover_interrupted_jobs(self) -> int:
        recovered = 0
        if not self.temp_dir.exists():
            return recovered
        for item in self.temp_dir.iterdir():
            if not item.is_dir() or not JOB_ID_RE.fullmatch(item.name):
                continue
            job = self.read_job(item.name)
            if job and job.status.transient:
                job.status = JobStatus.INTERRUPTED
                job.message = "This job was interrupted before completion."
                job.error_code = ErrorCode.PREPARATION_INTERRUPTED
                job.error_message = "Video preparation was interrupted. Retry the preparation."
                job.updated_at = utc_now_iso()
                self.write_job(job)
                self.cleanup_failed_job_media(job.job_id)
                recovered += 1
        if recovered:
            logger.info("Recovered %d interrupted jobs", recovered)
        return recovered

    def _dir_size(self, root: Path) -> int:
        if not root.exists():
            return 0
        total = 0
        for path in root.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
        return total

    def directory_size(self, root: Path) -> int:
        return self._dir_size(root)

    def prepared_video_count(self) -> int:
        if not self.downloads_dir.exists():
            return 0
        count = 0
        for item in self.downloads_dir.iterdir():
            if item.is_dir() and (item / "lecture.mp4").exists() and (item / "metadata.json").exists():
                count += 1
        return count

    def free_space_bytes(self) -> int:
        return shutil.disk_usage(self.downloads_dir).free

    def is_writable(self, directory: Path) -> bool:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=directory, delete=True):
                pass
            return True
        except OSError:
            return False

    def cleanup_stale(self, active_job_ids: Iterable[str] = ()) -> tuple[int, int]:
        active = set(active_job_ids)
        threshold = datetime.now(timezone.utc) - timedelta(hours=self.temp_retention_hours)
        removed = 0
        freed = 0
        if not self.temp_dir.exists():
            return removed, freed

        for item in list(self.temp_dir.iterdir()):
            if not item.is_dir() or item.name in active:
                continue
            try:
                modified = datetime.fromtimestamp(item.stat().st_mtime, timezone.utc)
            except OSError:
                continue
            if modified >= threshold:
                continue
            freed += self._dir_size(item)
            shutil.rmtree(item, ignore_errors=True)
            removed += 1
            logger.info("Removed stale workspace %s", item.name)
        return removed, freed
