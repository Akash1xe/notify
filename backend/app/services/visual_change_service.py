from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.adaptive_frame_stream import AdaptiveFrameStream
from app.services.frame_timeline_service import FrameTimelineService
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService
from app.services.visual_change_detector import ChangeKind, VisualChangeDetector

ProgressCallback = Callable[[float, str], None]
ADAPTIVE_ANALYSIS_VERSION = 2


@dataclass(frozen=True)
class AdaptiveVisualConfig:
    coarse_fps: float = settings.analysis_coarse_fps
    fine_fps: float = settings.analysis_fine_fps
    coarse_width: int = settings.analysis_coarse_width
    fine_width: int = settings.analysis_fine_width
    pre_padding_seconds: float = settings.analysis_pre_window_padding_seconds
    post_padding_seconds: float = settings.analysis_post_window_padding_seconds
    merge_gap_seconds: float = settings.analysis_window_merge_gap_seconds
    local_persistence_samples: int = 2
    quiet_close_seconds: float = 1.0

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


class VisualChangeService:
    """Adaptive two-pass visual scanner.

    Pass 1 samples the entire lecture at low FPS on small frames to locate activity.
    Pass 2 scans only padded/merged activity windows at higher FPS. The resulting
    frame-difference file is sparse event evidence rather than one record per source
    frame pair. This preserves temporal detail where teaching changes while skipping
    long static explanations.
    """

    def __init__(
        self,
        storage: StorageService,
        prepared: PreparedVideoService,
        timeline: FrameTimelineService,
        detector: VisualChangeDetector | None = None,
        config: AdaptiveVisualConfig | None = None,
        stream: AdaptiveFrameStream | None = None,
    ) -> None:
        self.storage = storage
        self.prepared = prepared
        self.timeline = timeline
        self.detector = detector or VisualChangeDetector()
        self.config = config or AdaptiveVisualConfig()
        self.stream = stream or AdaptiveFrameStream()

    def _activity_windows_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "activity-windows.jsonl"

    def _adaptive_summary_path(self, video_id: str) -> Path:
        return self.storage.analysis_dir(video_id) / "adaptive-analysis-summary.json"

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
        if int(summary.get("analysis_engine_version") or 0) != ADAPTIVE_ANALYSIS_VERSION:
            return None
        if summary.get("adaptive_config") != self.config.to_dict():
            return None
        stat = prepared.local_video_path.stat()
        if summary.get("source_size_bytes") != stat.st_size or summary.get("source_mtime_ns") != stat.st_mtime_ns:
            return None
        if summary.get("timeline_generated_at") != timeline.get("generated_at"):
            return None
        return summary

    @staticmethod
    def _merge_windows(raw: list[dict], duration: float, config: AdaptiveVisualConfig) -> list[dict]:
        if not raw:
            return []
        padded = [
            {
                **item,
                "start_seconds": max(0.0, float(item["start_seconds"]) - config.pre_padding_seconds),
                "end_seconds": min(duration, float(item["end_seconds"]) + config.post_padding_seconds),
            }
            for item in raw
        ]
        padded.sort(key=lambda item: float(item["start_seconds"]))
        merged: list[dict] = []
        for item in padded:
            if not merged or float(item["start_seconds"]) - float(merged[-1]["end_seconds"]) > config.merge_gap_seconds:
                merged.append({**item, "reasons": [str(item["reason"])], "coarse_sample_count": int(item.get("coarse_sample_count") or 0)})
                continue
            current = merged[-1]
            current["end_seconds"] = max(float(current["end_seconds"]), float(item["end_seconds"]))
            current["peak_score"] = max(float(current.get("peak_score") or 0.0), float(item.get("peak_score") or 0.0))
            current["scene_change"] = bool(current.get("scene_change")) or bool(item.get("scene_change"))
            current["structural_change"] = bool(current.get("structural_change")) or bool(item.get("structural_change"))
            current["coarse_sample_count"] = int(current.get("coarse_sample_count") or 0) + int(item.get("coarse_sample_count") or 0)
            reason = str(item["reason"])
            if reason not in current["reasons"]:
                current["reasons"].append(reason)
        for index, item in enumerate(merged):
            item["window_index"] = index
            item["start_seconds"] = round(float(item["start_seconds"]), 6)
            item["end_seconds"] = round(float(item["end_seconds"]), 6)
            item.pop("reason", None)
        return merged

    def _coarse_windows(self, video_id: str, progress: ProgressCallback, timeline: dict) -> tuple[list[dict], int]:
        prepared = self.prepared.get_prepared_video(video_id)
        assert prepared is not None
        duration = float(timeline.get("duration_seconds") or 0.0)
        source_fps = float(timeline.get("fps") or 0.0)
        source_width = int(timeline.get("width") or 0)
        source_height = int(timeline.get("height") or 0)
        expected = max(1, int(duration * self.config.coarse_fps))

        raw_windows: list[dict] = []
        previous = None
        stable_anchor = None
        previous_timestamp = 0.0
        activity_start: float | None = None
        last_activity = 0.0
        local_run = 0
        peak_score = 0.0
        saw_scene = False
        saw_structural = False
        sample_count = 0
        activity_samples = 0

        def close_window(end: float) -> None:
            nonlocal activity_start, peak_score, saw_scene, saw_structural, activity_samples
            if activity_start is None:
                return
            reason = "STRUCTURAL_ACTIVITY" if saw_structural else "PERSISTENT_LOCAL_CHANGE"
            if saw_scene:
                reason = "SCENE_TRANSITION"
            raw_windows.append({
                "start_seconds": activity_start,
                "end_seconds": max(activity_start, end),
                "reason": reason,
                "peak_score": round(peak_score, 4),
                "scene_change": saw_scene,
                "structural_change": saw_structural,
                "coarse_sample_count": activity_samples,
            })
            activity_start = None
            peak_score = 0.0
            saw_scene = False
            saw_structural = False
            activity_samples = 0

        for packet in self.stream.frames(
            prepared.local_video_path,
            fps=self.config.coarse_fps,
            source_fps=source_fps,
            source_width=source_width,
            source_height=source_height,
            target_width=self.config.coarse_width,
        ):
            signature = self.detector.signature(packet.image)
            sample_count += 1
            if previous is None:
                previous = signature
                stable_anchor = signature
                previous_timestamp = packet.timestamp_seconds
                continue

            pair = self.detector.compare(previous, signature)
            anchor = self.detector.compare(stable_anchor, signature) if stable_anchor is not None else pair
            if pair.kind == ChangeKind.LOCAL:
                local_run += 1
            elif pair.kind == ChangeKind.NONE:
                local_run = 0

            meaningful = (
                pair.kind in {ChangeKind.STRUCTURAL, ChangeKind.SCENE}
                or anchor.kind in {ChangeKind.STRUCTURAL, ChangeKind.SCENE}
                or (pair.kind == ChangeKind.LOCAL and (local_run >= self.config.local_persistence_samples or anchor.kind != ChangeKind.NONE))
            )
            if meaningful:
                if activity_start is None:
                    activity_start = previous_timestamp
                last_activity = packet.timestamp_seconds
                peak_score = max(peak_score, pair.change_score, anchor.change_score)
                saw_scene = saw_scene or pair.kind == ChangeKind.SCENE or anchor.kind == ChangeKind.SCENE
                saw_structural = saw_structural or pair.kind == ChangeKind.STRUCTURAL or anchor.kind == ChangeKind.STRUCTURAL
                activity_samples += 1
            elif activity_start is not None and packet.timestamp_seconds - last_activity >= self.config.quiet_close_seconds:
                close_window(last_activity)
                stable_anchor = signature
            elif activity_start is None and pair.kind == ChangeKind.NONE:
                stable_anchor = signature

            previous = signature
            previous_timestamp = packet.timestamp_seconds
            if sample_count % max(1, expected // 100) == 0:
                progress(min(42.0, sample_count / expected * 42.0), f"Coarse visual scan... {sample_count:,} samples")

        close_window(last_activity if activity_start is not None else duration)
        return self._merge_windows(raw_windows, duration, self.config), sample_count

    def scan(self, video_id: str, progress: ProgressCallback) -> dict:
        prepared = self.prepared.get_prepared_video(video_id)
        if not prepared:
            raise AppError(ErrorCode.VIDEO_NOT_PREPARED, "Prepare the lecture before visual change analysis.", 409)
        timeline = self.timeline.get_summary(video_id)
        if not timeline:
            raise AppError(ErrorCode.TIMELINE_NOT_FOUND, "Build the frame metadata before visual change analysis.", 409)
        existing = self.get_summary(video_id)
        if existing:
            return existing

        started = time.perf_counter()
        analysis_dir = self.storage.analysis_dir(video_id)
        analysis_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.storage.frame_differences_path(video_id)
        temp_path = output_path.with_suffix(".jsonl.tmp")
        windows_path = self._activity_windows_path(video_id)
        windows_temp = windows_path.with_suffix(".jsonl.tmp")
        temp_path.unlink(missing_ok=True)
        windows_temp.unlink(missing_ok=True)

        progress(1.0, "Starting adaptive coarse scan...")
        windows, coarse_samples = self._coarse_windows(video_id, progress, timeline)
        with windows_temp.open("w", encoding="utf-8") as handle:
            for item in windows:
                handle.write(json.dumps(item, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(windows_temp, windows_path)

        source_fps = float(timeline.get("fps") or 0.0)
        source_width = int(timeline.get("width") or 0)
        source_height = int(timeline.get("height") or 0)
        duration = float(timeline.get("duration_seconds") or 0.0)
        counts = {kind.value: 0 for kind in ChangeKind}
        fine_samples = 0
        compared_pairs = 0
        total_score = 0.0
        max_score = 0.0
        max_score_frame_index: int | None = None
        last_written_timestamp = 0.0
        last_written_frame = 0

        try:
            with temp_path.open("w", encoding="utf-8") as output:
                for window_index, window in enumerate(windows):
                    start = float(window["start_seconds"])
                    end = float(window["end_seconds"])
                    previous_packet = None
                    previous_signature = None
                    for packet in self.stream.frames(
                        prepared.local_video_path,
                        fps=self.config.fine_fps,
                        source_fps=source_fps,
                        source_width=source_width,
                        source_height=source_height,
                        target_width=self.config.fine_width,
                        start_seconds=start,
                        end_seconds=end,
                    ):
                        signature = self.detector.signature(packet.image)
                        fine_samples += 1
                        if previous_packet is not None and previous_signature is not None:
                            metrics = self.detector.compare(previous_signature, signature)
                            record = {
                                "previous_frame_index": previous_packet.frame_index,
                                "frame_index": packet.frame_index,
                                "previous_timestamp_seconds": round(previous_packet.timestamp_seconds, 6),
                                "timestamp_seconds": round(packet.timestamp_seconds, 6),
                                "delta_seconds": round(max(0.0, packet.timestamp_seconds - previous_packet.timestamp_seconds), 6),
                                "activity_window_index": window_index,
                                **metrics.to_dict(),
                            }
                            output.write(json.dumps(record, separators=(",", ":")) + "\n")
                            counts[metrics.kind.value] += 1
                            compared_pairs += 1
                            total_score += metrics.change_score
                            if metrics.change_score > max_score:
                                max_score = metrics.change_score
                                max_score_frame_index = packet.frame_index
                            last_written_timestamp = packet.timestamp_seconds
                            last_written_frame = packet.frame_index
                        previous_packet = packet
                        previous_signature = signature
                    pct = 45.0 + ((window_index + 1) / max(1, len(windows))) * 50.0
                    progress(min(95.0, pct), f"Fine scanning activity window {window_index + 1:,}/{len(windows):,}")

                # Static sentinels let downstream state detection preserve an initial
                # or final stable screen even when no activity window covers it.
                if compared_pairs == 0:
                    end_ts = min(duration, max(settings.analysis_stable_seconds, 0.1))
                    output.write(json.dumps({
                        "previous_frame_index": 0,
                        "frame_index": max(1, int(round(end_ts * source_fps))),
                        "previous_timestamp_seconds": 0.0,
                        "timestamp_seconds": round(end_ts, 6),
                        "delta_seconds": round(end_ts, 6),
                        "activity_window_index": None,
                        "kind": "NONE",
                        "mean_pixel_delta": 0.0,
                        "changed_pixel_ratio": 0.0,
                        "edge_change_ratio": 0.0,
                        "change_bbox_area_ratio": 0.0,
                        "change_score": 0.0,
                    }, separators=(",", ":")) + "\n")
                    counts[ChangeKind.NONE.value] += 1
                    compared_pairs = 1
                    last_written_timestamp = end_ts
                    last_written_frame = max(1, int(round(end_ts * source_fps)))
                if duration - last_written_timestamp >= settings.analysis_stable_seconds:
                    output.write(json.dumps({
                        "previous_frame_index": last_written_frame,
                        "frame_index": max(last_written_frame + 1, int(round(duration * source_fps)) - 1),
                        "previous_timestamp_seconds": round(last_written_timestamp, 6),
                        "timestamp_seconds": round(duration, 6),
                        "delta_seconds": round(duration - last_written_timestamp, 6),
                        "activity_window_index": None,
                        "kind": "NONE",
                        "mean_pixel_delta": 0.0,
                        "changed_pixel_ratio": 0.0,
                        "edge_change_ratio": 0.0,
                        "change_bbox_area_ratio": 0.0,
                        "change_score": 0.0,
                    }, separators=(",", ":")) + "\n")
                    counts[ChangeKind.NONE.value] += 1
                    compared_pairs += 1
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_path, output_path)

            source_frames = int(timeline.get("frame_count") or 0)
            analyzed_samples = coarse_samples + fine_samples
            reduction = max(0.0, 100.0 * (1.0 - analyzed_samples / max(1, source_frames)))
            wall = max(0.001, time.perf_counter() - started)
            stat = prepared.local_video_path.stat()
            summary = {
                "video_id": video_id,
                "status": "READY",
                "analysis_engine_version": ADAPTIVE_ANALYSIS_VERSION,
                "compared_frame_count": analyzed_samples,
                "compared_pair_count": compared_pairs,
                "no_change_count": counts[ChangeKind.NONE.value],
                "local_change_count": counts[ChangeKind.LOCAL.value],
                "structural_change_count": counts[ChangeKind.STRUCTURAL.value],
                "scene_change_count": counts[ChangeKind.SCENE.value],
                "change_pair_count": compared_pairs - counts[ChangeKind.NONE.value],
                "average_change_score": round(total_score / max(1, compared_pairs), 4),
                "max_change_score": round(max_score, 4),
                "max_change_frame_index": max_score_frame_index,
                "coverage_complete": True,
                "compared_every_consecutive_pair": False,
                "adaptive_sampling": True,
                "source_frame_count": source_frames,
                "coarse_sample_count": coarse_samples,
                "fine_sample_count": fine_samples,
                "analyzed_sample_count": analyzed_samples,
                "activity_window_count": len(windows),
                "activity_seconds": round(sum(float(w["end_seconds"]) - float(w["start_seconds"]) for w in windows), 3),
                "static_seconds_skipped": round(max(0.0, duration - sum(float(w["end_seconds"]) - float(w["start_seconds"]) for w in windows)), 3),
                "estimated_frame_reduction_percent": round(reduction, 2),
                "processing_wall_seconds": round(wall, 3),
                "analysis_real_time_factor": round(wall / max(0.001, duration), 4),
                "detector_config": self.detector.config.to_dict(),
                "adaptive_config": self.config.to_dict(),
                "generated_at": utc_now_iso(),
                "timeline_generated_at": timeline["generated_at"],
                "source_size_bytes": stat.st_size,
                "source_mtime_ns": stat.st_mtime_ns,
            }
            self.storage.write_frame_differences_summary(video_id, summary)
            with self._adaptive_summary_path(video_id).open("w", encoding="utf-8") as handle:
                json.dump(summary, handle, ensure_ascii=False, indent=2)
            progress(100.0, f"Adaptive visual scan ready. Analyzed {analyzed_samples:,} samples; avoided about {reduction:.1f}% of source frames.")
            return summary
        except AppError:
            temp_path.unlink(missing_ok=True)
            raise
        except (OSError, ValueError) as exc:
            temp_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.CHANGE_DETECTION_FAILED, "Adaptive visual analysis failed.", 500) from exc
