from __future__ import annotations

import json
import os
from typing import Callable

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.frame_reader import VideoFrameReader
from app.services.frame_timeline_service import FrameTimelineService
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService
from app.services.visual_change_detector import ChangeKind, VisualChangeDetector

ProgressCallback = Callable[[float, str], None]


class VisualChangeService:
    def __init__(
        self,
        storage: StorageService,
        prepared: PreparedVideoService,
        timeline: FrameTimelineService,
        detector: VisualChangeDetector | None = None,
    ) -> None:
        self.storage = storage
        self.prepared = prepared
        self.timeline = timeline
        self.detector = detector or VisualChangeDetector()

    def get_summary(self, video_id: str) -> dict | None:
        prepared = self.prepared.get_prepared_video(video_id)
        timeline = self.timeline.get_summary(video_id)
        if not prepared or not timeline:
            return None

        summary = self.storage.read_frame_differences_summary(video_id)
        differences = self.storage.frame_differences_path(video_id)
        if not summary or not differences.exists():
            return None

        stat = prepared.local_video_path.stat()
        if summary.get("source_size_bytes") != stat.st_size or summary.get("source_mtime_ns") != stat.st_mtime_ns:
            return None
        if summary.get("timeline_generated_at") != timeline.get("generated_at"):
            return None
        if summary.get("compared_frame_count") != timeline.get("frame_count"):
            return None
        return summary

    def scan(self, video_id: str, progress: ProgressCallback) -> dict:
        prepared = self.prepared.get_prepared_video(video_id)
        if not prepared:
            raise AppError(ErrorCode.VIDEO_NOT_PREPARED, "Prepare the lecture before visual change analysis.", 409)

        timeline_summary = self.timeline.get_summary(video_id)
        if not timeline_summary:
            raise AppError(ErrorCode.TIMELINE_NOT_FOUND, "Build the frame timeline before visual change analysis.", 409)

        existing = self.get_summary(video_id)
        if existing:
            return existing

        expected_frames = int(timeline_summary.get("frame_count") or 0)
        if expected_frames <= 0:
            raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "The frame timeline is empty or invalid.", 422)

        analysis_dir = self.storage.analysis_dir(video_id)
        analysis_dir.mkdir(parents=True, exist_ok=True)
        timeline_path = self.storage.frame_timeline_path(video_id)
        output_path = self.storage.frame_differences_path(video_id)
        temp_path = output_path.with_suffix(".jsonl.tmp")
        temp_path.unlink(missing_ok=True)

        counts = {kind.value: 0 for kind in ChangeKind}
        compared_pairs = 0
        decoded_frames = 0
        total_score = 0.0
        max_score = 0.0
        max_score_frame_index: int | None = None
        previous_signature = None
        previous_index: int | None = None
        previous_timestamp: float | None = None

        try:
            with (
                VideoFrameReader(prepared.local_video_path) as reader,
                timeline_path.open("r", encoding="utf-8") as timeline_handle,
                temp_path.open("w", encoding="utf-8") as output_handle,
            ):
                update_every = max(30, expected_frames // 200)

                for packet in reader.frames():
                    timeline_line = timeline_handle.readline()
                    if not timeline_line:
                        raise AppError(
                            ErrorCode.FRAME_SEQUENCE_MISMATCH,
                            "The video contains frames that are missing from the persisted timeline.",
                            422,
                        )
                    try:
                        timeline_entry = json.loads(timeline_line)
                        timeline_index = int(timeline_entry["frame_index"])
                        timestamp = float(timeline_entry["timestamp_seconds"])
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                        raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "The persisted frame timeline is invalid.", 422) from exc

                    if timeline_index != packet.frame_index:
                        raise AppError(
                            ErrorCode.FRAME_SEQUENCE_MISMATCH,
                            "Frame order no longer matches the persisted timeline.",
                            422,
                        )
                    if previous_index is not None and packet.frame_index != previous_index + 1:
                        raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "A decoded frame gap was detected.", 422)

                    signature = self.detector.signature(packet.image)
                    decoded_frames += 1

                    if previous_signature is not None and previous_index is not None and previous_timestamp is not None:
                        metrics = self.detector.compare(previous_signature, signature)
                        record = {
                            "previous_frame_index": previous_index,
                            "frame_index": packet.frame_index,
                            "previous_timestamp_seconds": round(previous_timestamp, 6),
                            "timestamp_seconds": round(timestamp, 6),
                            "delta_seconds": round(max(0.0, timestamp - previous_timestamp), 6),
                            **metrics.to_dict(),
                        }
                        output_handle.write(json.dumps(record, separators=(",", ":")) + "\n")
                        counts[metrics.kind.value] += 1
                        compared_pairs += 1
                        total_score += metrics.change_score
                        if metrics.change_score > max_score:
                            max_score = metrics.change_score
                            max_score_frame_index = packet.frame_index

                    previous_signature = signature
                    previous_index = packet.frame_index
                    previous_timestamp = timestamp

                    if decoded_frames % update_every == 0:
                        pct = decoded_frames / expected_frames * 100.0
                        progress(
                            min(99.0, pct),
                            f"Comparing consecutive frames... {decoded_frames:,}/{expected_frames:,}",
                        )

                if timeline_handle.read().strip():
                    raise AppError(
                        ErrorCode.FRAME_SEQUENCE_MISMATCH,
                        "The persisted timeline contains frames that were not decoded from the video.",
                        422,
                    )

                output_handle.flush()
                os.fsync(output_handle.fileno())

            if decoded_frames != expected_frames or compared_pairs != max(0, expected_frames - 1):
                raise AppError(
                    ErrorCode.FRAME_SEQUENCE_MISMATCH,
                    "Visual analysis did not cover every consecutive frame pair.",
                    422,
                )

            os.replace(temp_path, output_path)
            stat = prepared.local_video_path.stat()
            change_count = compared_pairs - counts[ChangeKind.NONE.value]
            summary = {
                "video_id": video_id,
                "status": "READY",
                "compared_frame_count": decoded_frames,
                "compared_pair_count": compared_pairs,
                "no_change_count": counts[ChangeKind.NONE.value],
                "local_change_count": counts[ChangeKind.LOCAL.value],
                "structural_change_count": counts[ChangeKind.STRUCTURAL.value],
                "scene_change_count": counts[ChangeKind.SCENE.value],
                "change_pair_count": change_count,
                "average_change_score": round(total_score / compared_pairs, 4) if compared_pairs else 0.0,
                "max_change_score": round(max_score, 4),
                "max_change_frame_index": max_score_frame_index,
                "coverage_complete": True,
                "compared_every_consecutive_pair": True,
                "detector_config": self.detector.config.to_dict(),
                "generated_at": utc_now_iso(),
                "timeline_generated_at": timeline_summary["generated_at"],
                "source_size_bytes": stat.st_size,
                "source_mtime_ns": stat.st_mtime_ns,
            }
            self.storage.write_frame_differences_summary(video_id, summary)
            return summary
        except AppError:
            temp_path.unlink(missing_ok=True)
            raise
        except (OSError, ValueError) as exc:
            temp_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.CHANGE_DETECTION_FAILED, "Visual frame comparison failed.", 500) from exc
