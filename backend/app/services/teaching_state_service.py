from __future__ import annotations

import json
import os
from typing import Callable, Iterator

from app.core.errors import AppError, ErrorCode
from app.models.job import utc_now_iso
from app.services.frame_timeline_service import FrameTimelineService
from app.services.prepared_video_service import PreparedVideoService
from app.services.storage_service import StorageService
from app.services.teaching_state_detector import TeachingCheckpoint, TeachingStateDetector, TeachingStateReason
from app.services.visual_change_service import VisualChangeService

ProgressCallback = Callable[[float, str], None]


class TeachingStateService:
    def __init__(
        self,
        storage: StorageService,
        prepared: PreparedVideoService,
        timeline: FrameTimelineService,
        changes: VisualChangeService,
        detector: TeachingStateDetector | None = None,
    ) -> None:
        self.storage = storage
        self.prepared = prepared
        self.timeline = timeline
        self.changes = changes
        self.detector = detector or TeachingStateDetector()

    def get_summary(self, video_id: str) -> dict | None:
        prepared = self.prepared.get_prepared_video(video_id)
        timeline = self.timeline.get_summary(video_id)
        changes = self.changes.get_summary(video_id)
        if not prepared or not timeline or not changes:
            return None

        summary = self.storage.read_teaching_states_summary(video_id)
        states_path = self.storage.teaching_states_path(video_id)
        if not summary or not states_path.exists():
            return None

        stat = prepared.local_video_path.stat()
        if summary.get("source_size_bytes") != stat.st_size or summary.get("source_mtime_ns") != stat.st_mtime_ns:
            return None
        if summary.get("timeline_generated_at") != timeline.get("generated_at"):
            return None
        if summary.get("changes_generated_at") != changes.get("generated_at"):
            return None
        return summary

    def _records(self, video_id: str, expected_pairs: int, progress: ProgressCallback) -> Iterator[dict]:
        path = self.storage.frame_differences_path(video_id)
        if not path.exists():
            raise AppError(ErrorCode.CHANGE_ANALYSIS_NOT_FOUND, "Visual change analysis is missing.", 409)

        seen = 0
        last_timestamp = -1.0
        update_every = max(30, expected_pairs // 200) if expected_pairs else 30
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        previous_index = int(record["previous_frame_index"])
                        frame_index = int(record["frame_index"])
                        previous_timestamp = float(record["previous_timestamp_seconds"])
                        timestamp = float(record["timestamp_seconds"])
                        kind = str(record["kind"])
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                        raise AppError(ErrorCode.TEACHING_STATE_FAILED, "The visual change map is invalid.", 422) from exc

                    if previous_index != seen or frame_index != seen + 1:
                        raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "The visual change map contains a frame gap or reordering.", 422)
                    if previous_timestamp < last_timestamp or timestamp < previous_timestamp:
                        raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "The visual change map contains non-monotonic timestamps.", 422)
                    if kind not in {"NONE", "LOCAL", "STRUCTURAL", "SCENE"}:
                        raise AppError(ErrorCode.TEACHING_STATE_FAILED, "The visual change map contains an unknown change type.", 422)

                    seen += 1
                    last_timestamp = timestamp
                    if seen % update_every == 0:
                        pct = (seen / expected_pairs * 100.0) if expected_pairs else 100.0
                        progress(min(99.0, pct), f"Detecting stable teaching states... {seen:,}/{expected_pairs:,} transitions")
                    yield record
        except AppError:
            raise
        except OSError as exc:
            raise AppError(ErrorCode.TEACHING_STATE_FAILED, "The visual change map could not be read.", 500) from exc

        if seen != expected_pairs:
            raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "Teaching-state detection did not inspect every visual transition.", 422)

    def scan(self, video_id: str, progress: ProgressCallback) -> dict:
        prepared = self.prepared.get_prepared_video(video_id)
        timeline = self.timeline.get_summary(video_id)
        changes = self.changes.get_summary(video_id)
        if not prepared:
            raise AppError(ErrorCode.VIDEO_NOT_PREPARED, "Prepare the lecture before teaching-state detection.", 409)
        if not timeline:
            raise AppError(ErrorCode.TIMELINE_NOT_FOUND, "Build the frame timeline before teaching-state detection.", 409)
        if not changes:
            raise AppError(ErrorCode.CHANGE_ANALYSIS_NOT_FOUND, "Analyze visual changes before teaching-state detection.", 409)

        existing = self.get_summary(video_id)
        if existing:
            return existing

        frame_count = int(timeline.get("frame_count") or 0)
        expected_pairs = int(changes.get("compared_pair_count") or 0)
        if frame_count <= 0 or expected_pairs != max(0, frame_count - 1):
            raise AppError(ErrorCode.FRAME_SEQUENCE_MISMATCH, "Frame and visual-change coverage do not agree.", 422)

        output_path = self.storage.teaching_states_path(video_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix(".jsonl.tmp")
        temp_path.unlink(missing_ok=True)

        reason_counts = {reason.value: 0 for reason in TeachingStateReason}
        checkpoint_count = 0
        first_checkpoint_timestamp: float | None = None
        last_checkpoint_timestamp: float | None = None
        last_checkpoint_frame = -1

        def write_checkpoint(handle, checkpoint: TeachingCheckpoint) -> None:
            nonlocal checkpoint_count, first_checkpoint_timestamp, last_checkpoint_timestamp, last_checkpoint_frame
            if checkpoint.frame_index <= last_checkpoint_frame:
                raise AppError(ErrorCode.TEACHING_STATE_FAILED, "Teaching checkpoints are not strictly ordered.", 422)
            payload = checkpoint.to_dict(checkpoint_count)
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
            reason_counts[checkpoint.reason.value] += 1
            checkpoint_count += 1
            first_checkpoint_timestamp = checkpoint.timestamp_seconds if first_checkpoint_timestamp is None else first_checkpoint_timestamp
            last_checkpoint_timestamp = checkpoint.timestamp_seconds
            last_checkpoint_frame = checkpoint.frame_index

        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                if frame_count == 1:
                    write_checkpoint(
                        handle,
                        TeachingCheckpoint(
                            frame_index=0,
                            timestamp_seconds=float(timeline.get("first_timestamp_seconds") or 0.0),
                            reason=TeachingStateReason.SINGLE_FRAME,
                            stability_seconds=0.0,
                            source_change_kind="NONE",
                            max_change_score_since_previous=0.0,
                            activity_pair_count_since_previous=0,
                            protected_before_transition=True,
                        ),
                    )
                else:
                    for checkpoint in self.detector.detect(self._records(video_id, expected_pairs, progress)):
                        if checkpoint.frame_index >= frame_count:
                            raise AppError(ErrorCode.TEACHING_STATE_FAILED, "A teaching checkpoint references a frame outside the timeline.", 422)
                        write_checkpoint(handle, checkpoint)

                if checkpoint_count == 0:
                    raise AppError(ErrorCode.TEACHING_STATE_FAILED, "No teaching-state checkpoint could be produced.", 422)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(temp_path, output_path)
            stat = prepared.local_video_path.stat()
            summary = {
                "video_id": video_id,
                "status": "READY",
                "checkpoint_count": checkpoint_count,
                "initial_stable_count": reason_counts[TeachingStateReason.INITIAL_STABLE.value],
                "stable_after_change_count": reason_counts[TeachingStateReason.STABLE_AFTER_CHANGE.value],
                "pre_transition_protection_count": reason_counts[TeachingStateReason.PRE_TRANSITION_PROTECTION.value],
                "end_of_video_fallback_count": reason_counts[TeachingStateReason.END_OF_VIDEO_FALLBACK.value],
                "single_frame_count": reason_counts[TeachingStateReason.SINGLE_FRAME.value],
                "first_checkpoint_timestamp_seconds": round(first_checkpoint_timestamp or 0.0, 6),
                "last_checkpoint_timestamp_seconds": round(last_checkpoint_timestamp or 0.0, 6),
                "coverage_complete": True,
                "source_pair_count": expected_pairs,
                "detector_config": self.detector.config.to_dict(),
                "generated_at": utc_now_iso(),
                "timeline_generated_at": timeline["generated_at"],
                "changes_generated_at": changes["generated_at"],
                "source_size_bytes": stat.st_size,
                "source_mtime_ns": stat.st_mtime_ns,
            }
            self.storage.write_teaching_states_summary(video_id, summary)
            progress(100.0, f"Stable teaching states ready. {checkpoint_count:,} checkpoint candidates found.")
            return summary
        except AppError:
            temp_path.unlink(missing_ok=True)
            raise
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.TEACHING_STATE_FAILED, "Teaching-state detection failed.", 500) from exc
