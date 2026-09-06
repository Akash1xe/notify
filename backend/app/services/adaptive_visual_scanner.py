from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Iterator

import numpy as np

from app.core.errors import AppError, ErrorCode
from app.services.visual_change_detector import ChangeKind, VisualChangeDetector

ProgressCallback = Callable[[float, str], None]
ANALYSIS_ENGINE_VERSION = 2


@dataclass(frozen=True)
class AdaptiveVisualConfig:
    coarse_fps: float = 4.0
    fine_fps: float = 12.0
    coarse_width: int = 320
    fine_width: int = 640
    stable_seconds: float = 1.25
    pre_window_padding_seconds: float = 1.0
    post_window_padding_seconds: float = 2.0
    window_merge_gap_seconds: float = 2.0
    cumulative_local_score: float = 2.0
    anchor_refresh_quiet_seconds: float = 1.0

    def __post_init__(self) -> None:
        if not 1 <= self.coarse_fps <= 10:
            raise ValueError("coarse_fps must be between 1 and 10")
        if not 4 <= self.fine_fps <= 30 or self.fine_fps < self.coarse_fps:
            raise ValueError("fine_fps must be between 4 and 30 and >= coarse_fps")
        if not 160 <= self.coarse_width <= 960 or not 320 <= self.fine_width <= 1280:
            raise ValueError("adaptive analysis width is outside the supported range")

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True)
class Sample:
    timestamp: float
    frame_index: int
    image: np.ndarray


class AdaptiveVisualScanner:
    def __init__(self, detector: VisualChangeDetector, config: AdaptiveVisualConfig | None = None) -> None:
        self.config = config or AdaptiveVisualConfig()
        self.coarse = VisualChangeDetector(replace(detector.config, target_width=self.config.coarse_width))
        self.fine = VisualChangeDetector(replace(detector.config, target_width=self.config.fine_width))
        self.ffmpeg = shutil.which("ffmpeg") or "ffmpeg"

    @staticmethod
    def _height(sw: int, sh: int, width: int) -> int:
        height = max(2, int(round(width * sh / sw)))
        return height if height % 2 == 0 else height + 1

    def _frames(self, path: Path, *, fps: float, width: int, sw: int, sh: int, source_fps: float,
                source_frames: int, start: float = 0.0, end: float | None = None) -> Iterator[Sample]:
        height = self._height(sw, sh, width)
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin"]
        if start > 0:
            cmd += ["-ss", f"{start:.6f}"]
        cmd += ["-i", str(path)]
        if end is not None:
            cmd += ["-t", f"{max(0.001, end - start):.6f}"]
        cmd += ["-an", "-sn", "-dn", "-vf", f"fps={fps:.6f},scale={width}:{height}:flags=area",
                "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=width * height * 6)
        except OSError as exc:
            raise AppError(ErrorCode.CHANGE_DETECTION_FAILED, "FFmpeg could not start adaptive sampling.", 500) from exc
        assert proc.stdout is not None and proc.stderr is not None
        size = width * height * 3
        index = 0
        try:
            while True:
                data = proc.stdout.read(size)
                if not data:
                    break
                if len(data) != size:
                    raise AppError(ErrorCode.CHANGE_DETECTION_FAILED, "FFmpeg returned an incomplete sampled frame.", 500)
                timestamp = start + index / fps
                frame_index = int(round(timestamp * source_fps)) if source_fps > 0 else index
                frame_index = min(source_frames - 1, max(0, frame_index)) if source_frames > 0 else frame_index
                image = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 3).copy()
                yield Sample(timestamp, frame_index, image)
                index += 1
        finally:
            proc.stdout.close()
            error = proc.stderr.read().decode("utf-8", errors="replace").strip()
            proc.stderr.close()
            code = proc.wait()
            if code != 0:
                raise AppError(ErrorCode.CHANGE_DETECTION_FAILED, f"FFmpeg adaptive sampling failed: {error[:220]}", 500)

    @staticmethod
    def _record(previous: Sample, current: Sample, metrics) -> dict:
        return {
            "previous_frame_index": previous.frame_index,
            "frame_index": current.frame_index,
            "previous_timestamp_seconds": round(previous.timestamp, 6),
            "timestamp_seconds": round(current.timestamp, 6),
            "delta_seconds": round(current.timestamp - previous.timestamp, 6),
            **metrics.to_dict(),
        }

    def _coarse_pass(self, path: Path, *, sw: int, sh: int, source_fps: float, source_frames: int,
                     duration: float, progress: ProgressCallback) -> tuple[list[dict], list[dict], int]:
        fps = min(self.config.coarse_fps, source_fps) if source_fps > 0 else self.config.coarse_fps
        expected = max(1, int(duration * fps) + 1)
        records: list[dict] = []
        raw: list[tuple[float, float, str, float, bool, bool]] = []
        previous = None
        previous_sig = None
        anchor_sig = None
        quiet_since = None
        local_streak = 0
        local_start = None
        count = 0
        for sample in self._frames(path, fps=fps, width=self.config.coarse_width, sw=sw, sh=sh,
                                   source_fps=source_fps, source_frames=source_frames):
            count += 1
            sig = self.coarse.signature(sample.image)
            if anchor_sig is None:
                anchor_sig = sig
            if previous is not None and previous_sig is not None and sample.frame_index > previous.frame_index:
                metrics = self.coarse.compare(previous_sig, sig)
                records.append(self._record(previous, sample, metrics))
                anchor_metrics = self.coarse.compare(anchor_sig, sig)
                if metrics.kind == ChangeKind.NONE:
                    local_streak, local_start = 0, None
                    quiet_since = previous.timestamp if quiet_since is None else quiet_since
                    if sample.timestamp - quiet_since >= self.config.anchor_refresh_quiet_seconds:
                        anchor_sig = sig
                else:
                    quiet_since = None
                    strong = metrics.kind in {ChangeKind.STRUCTURAL, ChangeKind.SCENE} or anchor_metrics.kind in {ChangeKind.STRUCTURAL, ChangeKind.SCENE}
                    cumulative = anchor_metrics.kind == ChangeKind.LOCAL and anchor_metrics.change_score >= self.config.cumulative_local_score
                    emit, reason, start = False, "PERSISTENT_LOCAL_CHANGE", previous.timestamp
                    if metrics.kind == ChangeKind.SCENE or anchor_metrics.kind == ChangeKind.SCENE:
                        emit, reason = True, "SCENE_TRANSITION"
                    elif strong:
                        emit, reason = True, "STRUCTURAL_ACTIVITY"
                    elif metrics.kind == ChangeKind.LOCAL:
                        if local_streak == 0:
                            local_start = previous.timestamp
                        local_streak += 1
                        if local_streak >= 2 or cumulative:
                            emit = True
                            reason = "CUMULATIVE_CONTENT_CHANGE" if cumulative else "PERSISTENT_LOCAL_CHANGE"
                            start = local_start if local_start is not None else start
                    if emit:
                        raw.append((start, sample.timestamp, reason, max(metrics.change_score, anchor_metrics.change_score),
                                    metrics.kind == ChangeKind.SCENE or anchor_metrics.kind == ChangeKind.SCENE,
                                    metrics.kind == ChangeKind.STRUCTURAL or anchor_metrics.kind == ChangeKind.STRUCTURAL))
            previous, previous_sig = sample, sig
            if count % max(1, expected // 100) == 0:
                progress(min(42.0, count / expected * 42.0), f"Adaptive coarse scan... {count:,}/{expected:,} samples")
        return records, self._merge(raw, duration), count

    def _merge(self, raw: list[tuple[float, float, str, float, bool, bool]], duration: float) -> list[dict]:
        merged: list[dict] = []
        for start, end, reason, score, scene, structural in raw:
            item = {"start_seconds": max(0.0, start - self.config.pre_window_padding_seconds),
                    "end_seconds": min(duration, end + self.config.post_window_padding_seconds),
                    "reasons": {reason}, "peak_score": score, "scene_change": scene,
                    "structural_change": structural, "coarse_event_count": 1}
            if merged and item["start_seconds"] - merged[-1]["end_seconds"] <= self.config.window_merge_gap_seconds:
                current = merged[-1]
                current["end_seconds"] = max(current["end_seconds"], item["end_seconds"])
                current["reasons"].update(item["reasons"])
                current["peak_score"] = max(current["peak_score"], score)
                current["scene_change"] |= scene
                current["structural_change"] |= structural
                current["coarse_event_count"] += 1
            else:
                merged.append(item)
        return [{"window_index": i, "start_seconds": round(x["start_seconds"], 6),
                 "end_seconds": round(x["end_seconds"], 6),
                 "duration_seconds": round(x["end_seconds"] - x["start_seconds"], 6),
                 "reasons": sorted(x["reasons"]), "peak_score": round(x["peak_score"], 4),
                 "scene_change": x["scene_change"], "structural_change": x["structural_change"],
                 "coarse_event_count": x["coarse_event_count"]} for i, x in enumerate(merged)]

    def _fine_records(self, path: Path, window: dict, *, sw: int, sh: int, source_fps: float,
                      source_frames: int) -> tuple[list[dict], int]:
        fps = min(self.config.fine_fps, source_fps) if source_fps > 0 else self.config.fine_fps
        previous = previous_sig = None
        records, count = [], 0
        for sample in self._frames(path, fps=fps, width=self.config.fine_width, sw=sw, sh=sh,
                                   source_fps=source_fps, source_frames=source_frames,
                                   start=float(window["start_seconds"]), end=float(window["end_seconds"])):
            count += 1
            sig = self.fine.signature(sample.image)
            if previous is not None and previous_sig is not None and sample.frame_index > previous.frame_index:
                records.append(self._record(previous, sample, self.fine.compare(previous_sig, sig)))
            previous, previous_sig = sample, sig
        return records, count

    def scan(self, path: Path, *, source_width: int, source_height: int, source_fps: float,
             source_frame_count: int, duration_seconds: float, progress: ProgressCallback) -> dict:
        started = time.perf_counter()
        coarse, windows, coarse_count = self._coarse_pass(
            path, sw=source_width, sh=source_height, source_fps=source_fps,
            source_frames=source_frame_count, duration=duration_seconds, progress=progress)
        progress(44.0, f"Coarse scan found {len(windows):,} activity window(s).")
        fine, fine_count = [], 0
        total_window_seconds = sum(float(x["duration_seconds"]) for x in windows)
        completed = 0.0
        for i, window in enumerate(windows):
            chunk, samples = self._fine_records(path, window, sw=source_width, sh=source_height,
                                                source_fps=source_fps, source_frames=source_frame_count)
            fine.extend(chunk)
            fine_count += samples
            completed += float(window["duration_seconds"])
            progress(44.0 + (completed / total_window_seconds if total_window_seconds else 1.0) * 51.0,
                     f"Fine scanning activity window {i + 1:,}/{len(windows):,}")
        def inside(ts: float) -> bool:
            return any(float(w["start_seconds"]) <= ts <= float(w["end_seconds"]) for w in windows)
        combined = [x for x in coarse if not inside(float(x["timestamp_seconds"]))] + fine
        combined.sort(key=lambda x: (float(x["timestamp_seconds"]), int(x["frame_index"])))
        records, last_ts, last_frame = [], -1.0, -1
        for item in combined:
            ts, frame = float(item["timestamp_seconds"]), int(item["frame_index"])
            if ts > last_ts and frame > last_frame:
                records.append(item)
                last_ts, last_frame = ts, frame
        wall = max(0.0, time.perf_counter() - started)
        analyzed = coarse_count + fine_count
        reduction = max(0.0, 100.0 * (1.0 - analyzed / source_frame_count)) if source_frame_count else 0.0
        progress(97.0, f"Adaptive scan complete. Analyzed {analyzed:,} samples instead of {source_frame_count:,} source frames.")
        return {"records": records, "activity_windows": windows, "metrics": {
            "analysis_engine_version": ANALYSIS_ENGINE_VERSION,
            "source_frame_count": source_frame_count,
            "video_duration_seconds": round(duration_seconds, 6),
            "coarse_sample_count": coarse_count,
            "fine_sample_count": fine_count,
            "analyzed_sample_count": analyzed,
            "activity_window_count": len(windows),
            "activity_seconds": round(total_window_seconds, 6),
            "static_seconds_skipped": round(max(0.0, duration_seconds - total_window_seconds), 6),
            "processing_wall_seconds": round(wall, 6),
            "analysis_real_time_factor": round(wall / duration_seconds, 6) if duration_seconds else 0.0,
            "estimated_frame_reduction_percent": round(reduction, 3),
            "config": self.config.to_dict(),
        }}
