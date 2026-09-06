from __future__ import annotations

import json
import os
from typing import Callable

import cv2

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService

ProgressCallback = Callable[[float, str], None]
TIMELINE_VERSION = 2


class FrameTimelineService:
    """Builds source timing metadata without decoding every source frame.

    The old implementation walked every frame only to persist frame index/timestamp
    pairs. Adaptive analysis now derives source-frame indexes from FPS and timestamps,
    so the timeline stage can be metadata-only and complete in near-constant time.
    """

    def __init__(self, storage: StorageService, prepared: PreparedVideoService) -> None:
        self.storage = storage
        self.prepared = prepared

    def get_summary(self, video_id: str) -> dict | None:
        prepared = self.prepared.get_prepared_video(video_id)
        if not prepared:
            return None
        summary = self.storage.read_frame_timeline_summary(video_id)
        timeline = self.storage.frame_timeline_path(video_id)
        if not summary or not timeline.exists():
            return None
        if int(summary.get("timeline_version") or 0) != TIMELINE_VERSION:
            return None
        stat = prepared.local_video_path.stat()
        if summary.get("source_size_bytes") != stat.st_size or summary.get("source_mtime_ns") != stat.st_mtime_ns:
            return None
        return summary

    def scan(self, video_id: str, progress: ProgressCallback) -> dict:
        prepared = self.prepared.get_prepared_video(video_id)
        if not prepared:
            raise AppError(ErrorCode.VIDEO_NOT_PREPARED, "Prepare the lecture before starting frame analysis.", 409)

        existing = self.get_summary(video_id)
        if existing:
            return existing

        progress(10.0, "Reading source video metadata...")
        capture = cv2.VideoCapture(str(prepared.local_video_path))
        if not capture.isOpened():
            capture.release()
            raise AppError(ErrorCode.VIDEO_READER_FAILED, "The prepared lecture could not be opened for frame metadata.", 422)

        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        finally:
            capture.release()

        duration = float(prepared.probe.duration_seconds or 0.0)
        if fps <= 0 or width <= 0 or height <= 0:
            raise AppError(ErrorCode.FRAME_SCAN_FAILED, "The prepared lecture has invalid video timing metadata.", 422)
        if frame_count <= 0 and duration > 0:
            frame_count = max(1, int(round(duration * fps)))
        if frame_count <= 0:
            raise AppError(ErrorCode.FRAME_SCAN_FAILED, "The prepared lecture has no readable video frames.", 422)
        if duration <= 0:
            duration = frame_count / fps

        analysis_dir = self.storage.analysis_dir(video_id)
        analysis_dir.mkdir(parents=True, exist_ok=True)
        timeline_path = self.storage.frame_timeline_path(video_id)
        temp_path = timeline_path.with_suffix(".jsonl.tmp")
        temp_path.unlink(missing_ok=True)

        last_timestamp = max(0.0, min(duration, (frame_count - 1) / fps))
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps({"frame_index": 0, "timestamp_seconds": 0.0}) + "\n")
                if frame_count > 1:
                    handle.write(json.dumps({"frame_index": frame_count - 1, "timestamp_seconds": round(last_timestamp, 6)}) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, timeline_path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.FRAME_SCAN_FAILED, "Frame metadata could not be persisted.", 500) from exc

        stat = prepared.local_video_path.stat()
        summary = {
            "video_id": video_id,
            "status": "READY",
            "timeline_version": TIMELINE_VERSION,
            "frame_count": frame_count,
            "fps": round(fps, 6),
            "width": width,
            "height": height,
            "duration_seconds": round(duration, 6),
            "first_timestamp_seconds": 0.0,
            "last_timestamp_seconds": round(last_timestamp, 6),
            "metadata_only": True,
            "generated_at": utc_now_iso(),
            "source_size_bytes": stat.st_size,
            "source_mtime_ns": stat.st_mtime_ns,
        }
        self.storage.write_frame_timeline_summary(video_id, summary)
        progress(100.0, f"Video metadata ready. {frame_count:,} source frames; no full-frame timeline decode required.")
        return summary
