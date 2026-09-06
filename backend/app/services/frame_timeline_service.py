from __future__ import annotations

import json
import os
from typing import Callable

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.frame_reader import VideoFrameReader
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService

ProgressCallback = Callable[[float, str], None]
TIMELINE_VERSION = 2


class FrameTimelineService:
    """Builds cheap source metadata instead of decoding every lecture frame."""

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

        analysis_dir = self.storage.analysis_dir(video_id)
        analysis_dir.mkdir(parents=True, exist_ok=True)
        timeline_path = self.storage.frame_timeline_path(video_id)
        temp_path = timeline_path.with_suffix(".jsonl.tmp")
        temp_path.unlink(missing_ok=True)
        try:
            progress(20.0, "Reading lecture stream metadata without decoding every frame...")
            with VideoFrameReader(prepared.local_video_path) as reader:
                metadata = reader.metadata
                assert metadata is not None
            duration = max(0.0, float(prepared.probe.duration_seconds))
            fps = max(0.0, float(metadata.fps))
            frame_count = int(metadata.frame_count_hint)
            if frame_count <= 0 and fps > 0 and duration > 0:
                frame_count = max(1, int(round(duration * fps)))
            if frame_count <= 0:
                raise AppError(ErrorCode.FRAME_SCAN_FAILED, "The prepared lecture does not expose a usable frame count.", 422)

            last_timestamp = min(duration, (frame_count - 1) / fps) if fps > 0 else duration
            anchors = [{"frame_index": 0, "timestamp_seconds": 0.0}]
            if frame_count > 1:
                anchors.append({"frame_index": frame_count - 1, "timestamp_seconds": round(last_timestamp, 6)})
            progress(70.0, "Persisting compact source timeline anchors...")
            with temp_path.open("w", encoding="utf-8") as handle:
                for anchor in anchors:
                    handle.write(json.dumps(anchor, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, timeline_path)

            stat = prepared.local_video_path.stat()
            summary = {
                "video_id": video_id,
                "status": "READY",
                "timeline_version": TIMELINE_VERSION,
                "timeline_mode": "METADATA_ONLY",
                "frame_count": frame_count,
                "decoded_frame_count": 0,
                "fps": round(fps, 6),
                "width": metadata.width,
                "height": metadata.height,
                "duration_seconds": round(duration, 6),
                "first_timestamp_seconds": 0.0,
                "last_timestamp_seconds": round(last_timestamp, 6),
                "generated_at": utc_now_iso(),
                "source_size_bytes": stat.st_size,
                "source_mtime_ns": stat.st_mtime_ns,
            }
            self.storage.write_frame_timeline_summary(video_id, summary)
            progress(100.0, f"Source timeline ready from metadata ({frame_count:,} source frames).")
            return summary
        except AppError:
            temp_path.unlink(missing_ok=True)
            raise
        except (OSError, ValueError) as exc:
            temp_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.FRAME_SCAN_FAILED, "Frame timeline metadata analysis failed.", 500) from exc
