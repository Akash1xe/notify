from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.frame_reader import VideoFrameReader
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService

ProgressCallback = Callable[[float, str], None]


class FrameTimelineService:
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

        frame_count = 0
        first_timestamp = 0.0
        last_timestamp = 0.0
        metadata = None
        try:
            with VideoFrameReader(prepared.local_video_path) as reader, temp_path.open("w", encoding="utf-8") as handle:
                metadata = reader.metadata
                assert metadata is not None
                update_every = max(30, metadata.frame_count_hint // 200) if metadata.frame_count_hint else 120
                for packet in reader.frames():
                    if frame_count == 0:
                        first_timestamp = packet.timestamp_seconds
                    last_timestamp = packet.timestamp_seconds
                    handle.write(json.dumps({"frame_index": packet.frame_index, "timestamp_seconds": round(packet.timestamp_seconds, 6)}) + "\n")
                    frame_count += 1
                    if frame_count % update_every == 0:
                        pct = (frame_count / metadata.frame_count_hint * 100.0) if metadata.frame_count_hint else 0.0
                        progress(min(99.0, pct), f"Reading frames... {frame_count:,} decoded")
                handle.flush()
                os.fsync(handle.fileno())

            if frame_count <= 0 or metadata is None:
                raise AppError(ErrorCode.FRAME_SCAN_FAILED, "No readable frames were found in the prepared lecture.", 422)
            os.replace(temp_path, timeline_path)
            stat = prepared.local_video_path.stat()
            summary = {
                "video_id": video_id,
                "status": "READY",
                "frame_count": frame_count,
                "fps": round(metadata.fps, 6),
                "width": metadata.width,
                "height": metadata.height,
                "duration_seconds": round(prepared.probe.duration_seconds, 6),
                "first_timestamp_seconds": round(first_timestamp, 6),
                "last_timestamp_seconds": round(last_timestamp, 6),
                "generated_at": utc_now_iso(),
                "source_size_bytes": stat.st_size,
                "source_mtime_ns": stat.st_mtime_ns,
            }
            self.storage.write_frame_timeline_summary(video_id, summary)
            return summary
        except AppError:
            temp_path.unlink(missing_ok=True)
            raise
        except (OSError, ValueError) as exc:
            temp_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.FRAME_SCAN_FAILED, "Frame timeline analysis failed.", 500) from exc
