from __future__ import annotations

import json
import os
from typing import Callable

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.adaptive_visual_scanner import ANALYSIS_ENGINE_VERSION, AdaptiveVisualConfig, AdaptiveVisualScanner
from app.services.frame_timeline_service import FrameTimelineService
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService
from app.services.visual_change_detector import ChangeKind, VisualChangeDetector

ProgressCallback = Callable[[float, str], None]


class VisualChangeService:
    """Adaptive visual analysis: coarse whole-video scan plus fine activity windows."""

    def __init__(
        self,
        storage: StorageService,
        prepared: PreparedVideoService,
        timeline: FrameTimelineService,
        detector: VisualChangeDetector | None = None,
        adaptive_config: AdaptiveVisualConfig | None = None,
    ) -> None:
        self.storage = storage
        self.prepared = prepared
        self.timeline = timeline
        self.detector = detector or VisualChangeDetector()
        self.adaptive_config = adaptive_config or AdaptiveVisualConfig(
            coarse_fps=settings.analysis_coarse_fps,
            fine_fps=settings.analysis_fine_fps,
            coarse_width=settings.analysis_coarse_width,
            fine_width=settings.analysis_fine_width,
            stable_seconds=settings.analysis_stable_seconds,
            pre_window_padding_seconds=settings.analysis_pre_window_padding_seconds,
            post_window_padding_seconds=settings.analysis_post_window_padding_seconds,
            window_merge_gap_seconds=settings.analysis_window_merge_gap_seconds,
        )
        self.scanner = AdaptiveVisualScanner(self.detector, self.adaptive_config)

    def _activity_windows_path(self, video_id: str):
        return self.storage.analysis_dir(video_id) / "activity-windows.jsonl"

    def get_summary(self, video_id: str) -> dict | None:
        prepared = self.prepared.get_prepared_video(video_id)
        timeline = self.timeline.get_summary(video_id)
        if not prepared or not timeline:
            return None
        summary = self.storage.read_frame_differences_summary(video_id)
        differences = self.storage.frame_differences_path(video_id)
        windows = self._activity_windows_path(video_id)
        if not summary or not differences.exists() or not windows.exists():
            return None
        if int(summary.get("analysis_engine_version") or 0) != ANALYSIS_ENGINE_VERSION:
            return None
        if summary.get("adaptive_config") != self.adaptive_config.to_dict():
            return None
        stat = prepared.local_video_path.stat()
        if summary.get("source_size_bytes") != stat.st_size or summary.get("source_mtime_ns") != stat.st_mtime_ns:
            return None
        if summary.get("timeline_generated_at") != timeline.get("generated_at"):
            return None
        if int(summary.get("source_frame_count") or 0) != int(timeline.get("frame_count") or 0):
            return None
        return summary

    @staticmethod
    def _write_jsonl(path, records: list[dict]) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.unlink(missing_ok=True)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with temp.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        except OSError:
            temp.unlink(missing_ok=True)
            raise

    def scan(self, video_id: str, progress: ProgressCallback) -> dict:
        prepared = self.prepared.get_prepared_video(video_id)
        if not prepared:
            raise AppError(ErrorCode.VIDEO_NOT_PREPARED, "Prepare the lecture before visual change analysis.", 409)
        timeline_summary = self.timeline.get_summary(video_id)
        if not timeline_summary:
            raise AppError(ErrorCode.TIMELINE_NOT_FOUND, "Build the source timeline before visual change analysis.", 409)
        existing = self.get_summary(video_id)
        if existing:
            return existing

        source_frames = int(timeline_summary.get("frame_count") or 0)
        source_fps = float(timeline_summary.get("fps") or 0.0)
        duration = float(timeline_summary.get("duration_seconds") or 0.0)
        width = int(timeline_summary.get("width") or 0)
        height = int(timeline_summary.get("height") or 0)
        if source_frames <= 0 or source_fps <= 0 or duration <= 0 or width <= 0 or height <= 0:
            raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "Source video metadata is incomplete for adaptive analysis.", 422)

        output_path = self.storage.frame_differences_path(video_id)
        windows_path = self._activity_windows_path(video_id)
        try:
            progress(1.0, "Starting adaptive lecture scan at low temporal resolution...")
            result = self.scanner.scan(
                prepared.local_video_path,
                source_width=width,
                source_height=height,
                source_fps=source_fps,
                source_frame_count=source_frames,
                duration_seconds=duration,
                progress=progress,
            )
            records = list(result["records"])
            windows = list(result["activity_windows"])
            metrics = dict(result["metrics"])
            if source_frames > 1 and not records:
                raise AppError(ErrorCode.CHANGE_DETECTION_FAILED, "Adaptive analysis produced no usable visual transitions.", 422)
            self._write_jsonl(output_path, records)
            self._write_jsonl(windows_path, windows)

            counts = {kind.value: 0 for kind in ChangeKind}
            total_score = 0.0
            max_score = 0.0
            max_score_frame_index: int | None = None
            for record in records:
                kind = str(record.get("kind") or "NONE")
                if kind not in counts:
                    raise AppError(ErrorCode.CHANGE_DETECTION_FAILED, "Adaptive analysis produced an unknown change type.", 422)
                counts[kind] += 1
                score = float(record.get("change_score") or 0.0)
                total_score += score
                if score > max_score:
                    max_score = score
                    max_score_frame_index = int(record.get("frame_index") or 0)

            pair_count = len(records)
            stat = prepared.local_video_path.stat()
            summary = {
                "video_id": video_id,
                "status": "READY",
                "analysis_engine_version": ANALYSIS_ENGINE_VERSION,
                "adaptive_sampling": True,
                "source_frame_count": source_frames,
                "compared_frame_count": int(metrics.get("analyzed_sample_count") or 0),
                "compared_pair_count": pair_count,
                "no_change_count": counts[ChangeKind.NONE.value],
                "local_change_count": counts[ChangeKind.LOCAL.value],
                "structural_change_count": counts[ChangeKind.STRUCTURAL.value],
                "scene_change_count": counts[ChangeKind.SCENE.value],
                "change_pair_count": pair_count - counts[ChangeKind.NONE.value],
                "average_change_score": round(total_score / pair_count, 4) if pair_count else 0.0,
                "max_change_score": round(max_score, 4),
                "max_change_frame_index": max_score_frame_index,
                "coverage_complete": True,
                "compared_every_consecutive_pair": False,
                "coarse_sample_count": int(metrics.get("coarse_sample_count") or 0),
                "fine_sample_count": int(metrics.get("fine_sample_count") or 0),
                "analyzed_sample_count": int(metrics.get("analyzed_sample_count") or 0),
                "activity_window_count": int(metrics.get("activity_window_count") or 0),
                "activity_seconds": float(metrics.get("activity_seconds") or 0.0),
                "static_seconds_skipped": float(metrics.get("static_seconds_skipped") or 0.0),
                "processing_wall_seconds": float(metrics.get("processing_wall_seconds") or 0.0),
                "analysis_real_time_factor": float(metrics.get("analysis_real_time_factor") or 0.0),
                "estimated_frame_reduction_percent": float(metrics.get("estimated_frame_reduction_percent") or 0.0),
                "adaptive_config": self.adaptive_config.to_dict(),
                "detector_config": self.detector.config.to_dict(),
                "generated_at": utc_now_iso(),
                "timeline_generated_at": timeline_summary["generated_at"],
                "source_size_bytes": stat.st_size,
                "source_mtime_ns": stat.st_mtime_ns,
            }
            self.storage.write_frame_differences_summary(video_id, summary)
            progress(100.0, f"Adaptive visual map ready. {summary['analyzed_sample_count']:,} samples analyzed; {summary['estimated_frame_reduction_percent']:.1f}% of source-frame work avoided.")
            return summary
        except AppError:
            output_path.with_suffix(".jsonl.tmp").unlink(missing_ok=True)
            windows_path.with_suffix(".jsonl.tmp").unlink(missing_ok=True)
            raise
        except (OSError, ValueError) as exc:
            output_path.with_suffix(".jsonl.tmp").unlink(missing_ok=True)
            windows_path.with_suffix(".jsonl.tmp").unlink(missing_ok=True)
            raise AppError(ErrorCode.CHANGE_DETECTION_FAILED, "Adaptive visual analysis failed.", 500) from exc
