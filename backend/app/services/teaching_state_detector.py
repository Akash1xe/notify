from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable, Iterator


class TeachingStateReason(str, Enum):
    INITIAL_STABLE = "INITIAL_STABLE"
    STABLE_AFTER_CHANGE = "STABLE_AFTER_CHANGE"
    PRE_TRANSITION_PROTECTION = "PRE_TRANSITION_PROTECTION"
    END_OF_VIDEO_FALLBACK = "END_OF_VIDEO_FALLBACK"
    SINGLE_FRAME = "SINGLE_FRAME"


@dataclass(frozen=True)
class TeachingStateConfig:
    # A teaching screen is considered stable after it remains visually unchanged
    # for this long. This prevents one screenshot per written character/stroke.
    stable_seconds: float = 1.25
    # A shorter quiet pause is still protected if a large transition immediately
    # follows it (for example, erasing a board or switching slides).
    transition_protection_seconds: float = 0.45
    # Avoid creating multiple checkpoints at effectively the same moment.
    minimum_checkpoint_gap_seconds: float = 0.50
    # A transition can be considered destructive even when the visual-change
    # classifier did not label it SCENE.
    strong_transition_changed_ratio: float = 0.12
    strong_transition_score: float = 35.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class TeachingCheckpoint:
    frame_index: int
    timestamp_seconds: float
    reason: TeachingStateReason
    stability_seconds: float
    source_change_kind: str
    max_change_score_since_previous: float
    activity_pair_count_since_previous: int
    protected_before_transition: bool

    def to_dict(self, checkpoint_index: int) -> dict[str, object]:
        return {
            "checkpoint_index": checkpoint_index,
            "frame_index": self.frame_index,
            "timestamp_seconds": round(self.timestamp_seconds, 6),
            "reason": self.reason.value,
            "stability_seconds": round(self.stability_seconds, 6),
            "source_change_kind": self.source_change_kind,
            "max_change_score_since_previous": round(self.max_change_score_since_previous, 4),
            "activity_pair_count_since_previous": self.activity_pair_count_since_previous,
            "protected_before_transition": self.protected_before_transition,
        }


class TeachingStateDetector:
    """Turns consecutive-frame change records into conservative teaching states.

    The detector intentionally does not try to decide whether a LOCAL change is a
    cursor or a newly written character. Instead, all activity keeps the current
    state pending until the screen becomes stable. This avoids losing educational
    content prematurely; later duplicate/semantic stages can remove redundant
    candidates safely.
    """

    def __init__(self, config: TeachingStateConfig | None = None) -> None:
        self.config = config or TeachingStateConfig()

    def detect(self, records: Iterable[dict]) -> Iterator[TeachingCheckpoint]:
        config = self.config
        pending_content = True
        segment_had_change = False
        quiet_start_timestamp: float | None = None
        quiet_start_frame: int | None = None
        last_checkpoint_timestamp = float("-inf")
        last_checkpoint_frame = -1
        max_change_score = 0.0
        activity_pairs = 0
        last_change_kind = "NONE"
        last_record: dict | None = None
        saw_any_record = False

        def can_emit(frame_index: int, timestamp: float) -> bool:
            if frame_index <= last_checkpoint_frame:
                return False
            return timestamp - last_checkpoint_timestamp >= config.minimum_checkpoint_gap_seconds

        def build_checkpoint(
            *,
            frame_index: int,
            timestamp: float,
            reason: TeachingStateReason,
            stability_seconds: float,
            protected: bool,
        ) -> TeachingCheckpoint:
            return TeachingCheckpoint(
                frame_index=frame_index,
                timestamp_seconds=timestamp,
                reason=reason,
                stability_seconds=max(0.0, stability_seconds),
                source_change_kind=last_change_kind,
                max_change_score_since_previous=max_change_score,
                activity_pair_count_since_previous=activity_pairs,
                protected_before_transition=protected,
            )

        for record in records:
            saw_any_record = True
            last_record = record
            kind = str(record["kind"])
            previous_frame = int(record["previous_frame_index"])
            frame_index = int(record["frame_index"])
            previous_timestamp = float(record["previous_timestamp_seconds"])
            timestamp = float(record["timestamp_seconds"])
            changed_ratio = float(record.get("changed_pixel_ratio", 0.0))
            change_score = float(record.get("change_score", 0.0))

            if kind == "NONE":
                if quiet_start_timestamp is None:
                    quiet_start_timestamp = previous_timestamp
                    quiet_start_frame = previous_frame

                stable_duration = max(0.0, timestamp - quiet_start_timestamp)
                if pending_content and stable_duration >= config.stable_seconds and can_emit(frame_index, timestamp):
                    reason = (
                        TeachingStateReason.STABLE_AFTER_CHANGE
                        if segment_had_change or last_checkpoint_frame >= 0
                        else TeachingStateReason.INITIAL_STABLE
                    )
                    checkpoint = build_checkpoint(
                        frame_index=frame_index,
                        timestamp=timestamp,
                        reason=reason,
                        stability_seconds=stable_duration,
                        protected=False,
                    )
                    yield checkpoint
                    last_checkpoint_timestamp = checkpoint.timestamp_seconds
                    last_checkpoint_frame = checkpoint.frame_index
                    pending_content = False
                    segment_had_change = False
                    max_change_score = 0.0
                    activity_pairs = 0
                    last_change_kind = "NONE"
                continue

            # The current frame changed. If a quiet teaching state existed just
            # before a destructive/large transition but was shorter than the full
            # stability threshold, protect its previous frame before it vanishes.
            strong_transition = (
                kind == "SCENE"
                or changed_ratio >= config.strong_transition_changed_ratio
                or change_score >= config.strong_transition_score
            )
            quiet_duration = (
                max(0.0, previous_timestamp - quiet_start_timestamp)
                if quiet_start_timestamp is not None
                else 0.0
            )
            if (
                strong_transition
                and pending_content
                and quiet_start_timestamp is not None
                and quiet_duration >= config.transition_protection_seconds
                and can_emit(previous_frame, previous_timestamp)
            ):
                checkpoint = build_checkpoint(
                    frame_index=previous_frame,
                    timestamp=previous_timestamp,
                    reason=TeachingStateReason.PRE_TRANSITION_PROTECTION,
                    stability_seconds=quiet_duration,
                    protected=True,
                )
                yield checkpoint
                last_checkpoint_timestamp = checkpoint.timestamp_seconds
                last_checkpoint_frame = checkpoint.frame_index
                max_change_score = 0.0
                activity_pairs = 0

            pending_content = True
            segment_had_change = True
            quiet_start_timestamp = None
            quiet_start_frame = None
            max_change_score = max(max_change_score, change_score)
            activity_pairs += 1
            last_change_kind = kind

        # A one-frame video has no pair records. The service handles that case
        # because it owns the timeline metadata needed to reference frame zero.
        if not saw_any_record or last_record is None:
            return

        final_frame = int(last_record["frame_index"])
        final_timestamp = float(last_record["timestamp_seconds"])
        final_stability = (
            max(0.0, final_timestamp - quiet_start_timestamp)
            if quiet_start_timestamp is not None
            else 0.0
        )
        if pending_content and can_emit(final_frame, final_timestamp):
            yield build_checkpoint(
                frame_index=final_frame,
                timestamp=final_timestamp,
                reason=TeachingStateReason.END_OF_VIDEO_FALLBACK,
                stability_seconds=final_stability,
                protected=True,
            )
