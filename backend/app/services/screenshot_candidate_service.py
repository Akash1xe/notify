from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService
from app.services.teaching_state_service import TeachingStateService

ProgressCallback = Callable[[float, str], None]
PIPELINE_VERSION = 2


@dataclass(frozen=True)
class ScreenshotCandidateConfig:
    jpeg_quality: int = 92
    hash_size: int = 8
    max_hash_distance: int = 2
    max_mean_abs_difference: float = 1.75
    comparison_width: int = 160
    comparison_height: int = 90
    recent_comparison_window: int = 5
    content_loss_edge_ratio: float = 0.60
    content_loss_contrast_ratio: float = 0.85
    minimum_edge_density_for_loss_check: float = 0.003

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True)
class Fingerprint:
    dhash: int
    thumbnail: np.ndarray


@dataclass(frozen=True)
class KeptCandidate:
    candidate_index: int
    fingerprint: Fingerprint


class ScreenshotCandidateService:
    def __init__(
        self,
        storage: StorageService,
        prepared: PreparedVideoService,
        states: TeachingStateService,
        config: ScreenshotCandidateConfig | None = None,
    ) -> None:
        self.storage = storage
        self.prepared = prepared
        self.states = states
        self.config = config or ScreenshotCandidateConfig()

    def get_summary(self, video_id: str) -> dict | None:
        prepared = self.prepared.get_prepared_video(video_id)
        states = self.states.get_summary(video_id)
        if not prepared or not states:
            return None

        summary = self.storage.read_screenshot_candidates_summary(video_id)
        manifest_path = self.storage.screenshot_candidates_path(video_id)
        images_dir = self.storage.screenshot_candidates_dir(video_id)
        if not summary or not manifest_path.exists() or not images_dir.exists():
            return None
        if int(summary.get("pipeline_version") or 0) != PIPELINE_VERSION:
            return None

        stat = prepared.local_video_path.stat()
        if summary.get("source_size_bytes") != stat.st_size or summary.get("source_mtime_ns") != stat.st_mtime_ns:
            return None
        if summary.get("states_generated_at") != states.get("generated_at"):
            return None
        if int(summary.get("source_checkpoint_count") or -1) != int(states.get("checkpoint_count") or 0):
            return None

        kept_count = int(summary.get("kept_candidate_count") or 0)
        try:
            actual_images = sum(1 for path in images_dir.iterdir() if path.is_file() and path.suffix.lower() == ".jpg")
        except OSError:
            return None
        if actual_images != kept_count:
            return None
        return summary

    def _state_records(self, video_id: str, expected_count: int) -> Iterator[dict]:
        path = self.storage.teaching_states_path(video_id)
        if not path.exists():
            raise AppError(ErrorCode.TEACHING_STATES_NOT_FOUND, "Stable teaching states are missing.", 409)

        seen = 0
        last_frame = -1
        last_timestamp = -1.0
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        checkpoint_index = int(record["checkpoint_index"])
                        frame_index = int(record["frame_index"])
                        timestamp = float(record["timestamp_seconds"])
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                        raise AppError(ErrorCode.SCREENSHOT_EXTRACTION_FAILED, "The teaching-state checkpoint file is invalid.", 422) from exc

                    if checkpoint_index != seen or frame_index <= last_frame or timestamp < last_timestamp:
                        raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "Teaching-state checkpoints contain a gap or reordering.", 422)
                    seen += 1
                    last_frame = frame_index
                    last_timestamp = timestamp
                    yield record
        except AppError:
            raise
        except OSError as exc:
            raise AppError(ErrorCode.SCREENSHOT_EXTRACTION_FAILED, "Teaching-state checkpoints could not be read.", 500) from exc

        if seen != expected_count:
            raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "Teaching-state checkpoint coverage does not match its summary.", 422)

    def fingerprint(self, frame: np.ndarray) -> Fingerprint:
        if frame.size == 0:
            raise AppError(ErrorCode.SCREENSHOT_EXTRACTION_FAILED, "An empty video frame could not be fingerprinted.", 422)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hash_image = cv2.resize(gray, (self.config.hash_size + 1, self.config.hash_size), interpolation=cv2.INTER_AREA)
        diff = hash_image[:, 1:] > hash_image[:, :-1]
        value = 0
        for bit in diff.flatten():
            value = (value << 1) | int(bool(bit))
        thumbnail = cv2.resize(
            gray,
            (self.config.comparison_width, self.config.comparison_height),
            interpolation=cv2.INTER_AREA,
        )
        return Fingerprint(dhash=value, thumbnail=thumbnail)

    def detail_metrics(self, frame: np.ndarray) -> tuple[float, float]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        reduced = cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)
        edges = cv2.Canny(reduced, 60, 160)
        edge_density = float(np.mean(edges > 0))
        contrast_std = float(np.std(reduced) / 255.0)
        return edge_density, contrast_std

    @staticmethod
    def hash_distance(left: Fingerprint, right: Fingerprint) -> int:
        return (left.dhash ^ right.dhash).bit_count()

    @staticmethod
    def mean_abs_difference(left: Fingerprint, right: Fingerprint) -> float:
        return float(np.mean(cv2.absdiff(left.thumbnail, right.thumbnail)))

    def find_duplicate(self, fingerprint: Fingerprint, recent: list[KeptCandidate]) -> tuple[int | None, int | None, float | None]:
        for candidate in reversed(recent[-self.config.recent_comparison_window :]):
            distance = self.hash_distance(fingerprint, candidate.fingerprint)
            if distance > self.config.max_hash_distance:
                continue
            mean_difference = self.mean_abs_difference(fingerprint, candidate.fingerprint)
            if mean_difference <= self.config.max_mean_abs_difference:
                return candidate.candidate_index, distance, mean_difference
        return None, None, None

    def mark_content_loss_risks(self, records: list[dict]) -> int:
        risk_count = 0
        for record in records:
            record["content_loss_risk"] = False
            record["content_loss_reason"] = None

        for index in range(len(records) - 1):
            current = records[index]
            following = records[index + 1]
            scene_replacement = str(following.get("source_change_kind") or "NONE") == "SCENE"
            current_edges = float(current.get("edge_density") or 0.0)
            next_edges = float(following.get("edge_density") or 0.0)
            current_contrast = float(current.get("contrast_std") or 0.0)
            next_contrast = float(following.get("contrast_std") or 0.0)
            sharp_detail_drop = (
                current_edges >= self.config.minimum_edge_density_for_loss_check
                and next_edges <= current_edges * self.config.content_loss_edge_ratio
                and next_contrast <= max(0.01, current_contrast * self.config.content_loss_contrast_ratio)
            )
            if scene_replacement or sharp_detail_drop:
                current["content_loss_risk"] = True
                current["content_loss_reason"] = "SCENE_REPLACEMENT" if scene_replacement else "DETAIL_DROP"
                risk_count += 1
        return risk_count

    def _write_jpeg(self, path: Path, frame: np.ndarray) -> None:
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.config.jpeg_quality])
        if not ok:
            raise AppError(ErrorCode.SCREENSHOT_EXTRACTION_FAILED, "A screenshot candidate could not be encoded.", 500)
        try:
            path.write_bytes(encoded.tobytes())
        except OSError as exc:
            raise AppError(ErrorCode.SCREENSHOT_EXTRACTION_FAILED, "A screenshot candidate could not be saved locally.", 500) from exc

    def scan(self, video_id: str, progress: ProgressCallback) -> dict:
        prepared = self.prepared.get_prepared_video(video_id)
        states = self.states.get_summary(video_id)
        if not prepared:
            raise AppError(ErrorCode.VIDEO_NOT_PREPARED, "Prepare the lecture before screenshot extraction.", 409)
        if not states:
            raise AppError(ErrorCode.TEACHING_STATES_NOT_FOUND, "Detect stable teaching states before screenshot extraction.", 409)

        existing = self.get_summary(video_id)
        if existing:
            return existing

        expected_count = int(states.get("checkpoint_count") or 0)
        if expected_count <= 0:
            raise AppError(ErrorCode.SCREENSHOT_EXTRACTION_FAILED, "No teaching-state checkpoints are available for screenshot extraction.", 422)

        state_records = list(self._state_records(video_id, expected_count))
        target_by_frame = {int(record["frame_index"]): record for record in state_records}
        if len(target_by_frame) != expected_count:
            raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "Multiple teaching-state checkpoints reference the same video frame.", 422)
        last_target_frame = max(target_by_frame)

        output_manifest = self.storage.screenshot_candidates_path(video_id)
        output_manifest.parent.mkdir(parents=True, exist_ok=True)
        temp_manifest = output_manifest.with_suffix(".jsonl.tmp")
        final_images_dir = self.storage.screenshot_candidates_dir(video_id)
        temp_images_dir = final_images_dir.with_name(final_images_dir.name + ".tmp")
        temp_manifest.unlink(missing_ok=True)
        if temp_images_dir.exists():
            shutil.rmtree(temp_images_dir, ignore_errors=True)
        temp_images_dir.mkdir(parents=True, exist_ok=True)

        capture = cv2.VideoCapture(str(prepared.local_video_path))
        if not capture.isOpened():
            shutil.rmtree(temp_images_dir, ignore_errors=True)
            raise AppError(ErrorCode.VIDEO_READER_FAILED, "The prepared lecture could not be opened for screenshot extraction.", 422)

        recent_kept: list[KeptCandidate] = []
        candidate_index = 0
        kept_count = 0
        duplicate_count = 0
        protected_kept_count = 0
        current_frame_index = 0
        payloads: list[dict] = []

        try:
            while current_frame_index <= last_target_frame:
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise AppError(ErrorCode.SCREENSHOT_EXTRACTION_FAILED, "The video ended before every teaching checkpoint could be extracted.", 422)

                state = target_by_frame.get(current_frame_index)
                if state is not None:
                    fingerprint = self.fingerprint(frame)
                    edge_density, contrast_std = self.detail_metrics(frame)
                    protected = bool(state.get("protected_before_transition")) or str(state.get("reason")) in {
                        "PRE_TRANSITION_PROTECTION",
                        "END_OF_VIDEO_FALLBACK",
                        "SINGLE_FRAME",
                    }
                    duplicate_of, hash_distance, mean_difference = self.find_duplicate(fingerprint, recent_kept)
                    keep = protected or duplicate_of is None
                    filename: str | None = None

                    if keep:
                        filename = f"candidate-{candidate_index:06d}.jpg"
                        self._write_jpeg(temp_images_dir / filename, frame)
                        recent_kept.append(KeptCandidate(candidate_index=candidate_index, fingerprint=fingerprint))
                        kept_count += 1
                        if protected:
                            protected_kept_count += 1
                    else:
                        duplicate_count += 1

                    payloads.append(
                        {
                            "candidate_index": candidate_index,
                            "checkpoint_index": int(state["checkpoint_index"]),
                            "frame_index": current_frame_index,
                            "timestamp_seconds": float(state["timestamp_seconds"]),
                            "reason": str(state.get("reason") or "UNKNOWN"),
                            "source_change_kind": str(state.get("source_change_kind") or "NONE"),
                            "protected": protected,
                            "kept": keep,
                            "image_filename": filename,
                            "duplicate_of_candidate_index": duplicate_of if not keep else None,
                            "duplicate_hash_distance": hash_distance,
                            "duplicate_mean_abs_difference": round(mean_difference, 4) if mean_difference is not None else None,
                            "edge_density": round(edge_density, 6),
                            "contrast_std": round(contrast_std, 6),
                        }
                    )
                    candidate_index += 1
                    pct = candidate_index / expected_count * 100.0
                    progress(min(96.0, pct * 0.96), f"Extracting screenshot candidates... {candidate_index:,}/{expected_count:,}")

                current_frame_index += 1

            if candidate_index != expected_count:
                raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "Not every teaching checkpoint produced a screenshot candidate record.", 422)

            risk_count = self.mark_content_loss_risks(payloads)
            progress(97.0, "Checking candidates for content-loss risk...")
            with temp_manifest.open("w", encoding="utf-8") as manifest:
                for payload in payloads:
                    manifest.write(json.dumps(payload, separators=(",", ":")) + "\n")
                manifest.flush()
                os.fsync(manifest.fileno())

            capture.release()
            if final_images_dir.exists():
                shutil.rmtree(final_images_dir)
            os.replace(temp_images_dir, final_images_dir)
            os.replace(temp_manifest, output_manifest)

            stat = prepared.local_video_path.stat()
            summary = {
                "video_id": video_id,
                "status": "READY",
                "pipeline_version": PIPELINE_VERSION,
                "source_checkpoint_count": expected_count,
                "kept_candidate_count": kept_count,
                "duplicate_candidate_count": duplicate_count,
                "protected_kept_count": protected_kept_count,
                "content_loss_risk_count": risk_count,
                "deduplication_conservative": True,
                "filter_config": self.config.to_dict(),
                "generated_at": utc_now_iso(),
                "states_generated_at": states["generated_at"],
                "source_size_bytes": stat.st_size,
                "source_mtime_ns": stat.st_mtime_ns,
            }
            self.storage.write_screenshot_candidates_summary(video_id, summary)
            progress(100.0, f"Screenshot candidates ready. Kept {kept_count:,}; removed {duplicate_count:,} near-duplicates.")
            return summary
        except AppError:
            capture.release()
            temp_manifest.unlink(missing_ok=True)
            shutil.rmtree(temp_images_dir, ignore_errors=True)
            raise
        except (OSError, cv2.error) as exc:
            capture.release()
            temp_manifest.unlink(missing_ok=True)
            shutil.rmtree(temp_images_dir, ignore_errors=True)
            raise AppError(ErrorCode.SCREENSHOT_EXTRACTION_FAILED, "Screenshot candidate extraction failed.", 500) from exc
