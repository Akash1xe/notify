from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Callable, Any

import yt_dlp

from app.core.errors import AppError, ErrorCode
from app.models.job import JobStatus
from app.schemas.video import VideoMetadata
from app.services.media_service import MediaService
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[JobStatus, float, str], None]


class VideoDownloadService:
    def __init__(
        self,
        storage: StorageService,
        media: MediaService,
        max_video_height: int,
        min_free_space_bytes: int,
    ) -> None:
        self.storage = storage
        self.media = media
        self.max_video_height = max_video_height
        self.min_free_space_bytes = min_free_space_bytes

    def _find_media_candidate(self, source_dir: Path) -> Path:
        allowed = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
        candidates = [
            path for path in source_dir.iterdir()
            if path.is_file() and path.suffix.lower() in allowed and not path.name.endswith(".part")
        ]
        if not candidates:
            raise AppError(ErrorCode.DOWNLOAD_FAILED, "Video download failed.", 500)
        return max(candidates, key=lambda path: path.stat().st_size)

    def prepare(self, job_id: str, metadata: VideoMetadata, on_progress: ProgressCallback) -> Path:
        self.media.require_tools()
        if self.storage.free_space_bytes() < self.min_free_space_bytes:
            raise AppError(ErrorCode.INSUFFICIENT_DISK_SPACE, "Not enough free disk space is available to prepare this video.", 507)

        workspace = self.storage.create_job_workspace(job_id)
        source_dir = workspace / "source"
        processing_dir = workspace / "processing"
        output_template = str(source_dir / "download.%(ext)s")

        def progress_hook(data: dict[str, Any]) -> None:
            if data.get("status") != "downloading":
                return
            downloaded = float(data.get("downloaded_bytes") or 0)
            total = float(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
            if total > 0:
                percent = min(88.0, max(1.0, downloaded / total * 88.0))
            else:
                percent = 5.0
            on_progress(JobStatus.DOWNLOADING, percent, "Downloading video...")

        def postprocessor_hook(data: dict[str, Any]) -> None:
            if data.get("status") == "started":
                on_progress(JobStatus.MERGING, 90.0, "Merging media...")

        format_selector = (
            f"bv*[height<={self.max_video_height}]+ba/"
            f"b[height<={self.max_video_height}]/best"
        )
        options: dict[str, Any] = {
            "format": format_selector,
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "continuedl": True,
            "nopart": False,
        }

        on_progress(JobStatus.DOWNLOADING, 1.0, "Downloading video...")
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.extract_info(metadata.normalized_url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            logger.warning("yt-dlp download failed for video_id=%s", metadata.video_id)
            raise AppError(ErrorCode.DOWNLOAD_FAILED, "Video download failed.", 500) from exc
        except Exception as exc:
            logger.exception("Unexpected download failure for video_id=%s", metadata.video_id)
            raise AppError(ErrorCode.DOWNLOAD_FAILED, "Video download failed.", 500) from exc

        candidate = self._find_media_candidate(source_dir)
        prepared_candidate = candidate
        if candidate.suffix.lower() != ".mp4":
            on_progress(JobStatus.MERGING, 92.0, "Preparing MP4 media...")
            prepared_candidate = processing_dir / "prepared.mp4"
            self.media.normalize_to_mp4(candidate, prepared_candidate)

        on_progress(JobStatus.VERIFYING, 96.0, "Verifying video...")
        probe = self.media.verify(prepared_candidate, expected_duration=metadata.duration_seconds)

        # If yt-dlp produced an MP4 in the source directory, copy it into the processing
        # directory before finalization so the source path remains inside the isolated job.
        if prepared_candidate == candidate and prepared_candidate.parent == source_dir:
            normalized = processing_dir / "prepared.mp4"
            shutil.copy2(prepared_candidate, normalized)
            prepared_candidate = normalized

        on_progress(JobStatus.FINALIZING, 98.0, "Finalizing local video...")
        effective_resolution = f"{probe.height}p" if probe.height else metadata.resolution
        manifest = metadata.model_dump()
        manifest["resolution"] = effective_resolution
        final_path = self.storage.finalize_video(job_id, metadata.video_id, prepared_candidate, manifest)
        return final_path
