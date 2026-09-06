from app.services.teaching_state_detector import TeachingStateConfig, TeachingStateDetector, TeachingStateReason


def record(index: int, timestamp: float, kind: str, *, score: float = 0.0, changed_ratio: float = 0.0) -> dict:
    return {
        "previous_frame_index": index - 1,
        "frame_index": index,
        "previous_timestamp_seconds": timestamp - 0.1,
        "timestamp_seconds": timestamp,
        "kind": kind,
        "change_score": score,
        "changed_pixel_ratio": changed_ratio,
    }


def test_continuous_writing_waits_for_stability() -> None:
    detector = TeachingStateDetector(TeachingStateConfig(stable_seconds=0.5, minimum_checkpoint_gap_seconds=0.2))
    records = []

    # Initial slide becomes stable.
    for index in range(1, 7):
        records.append(record(index, index * 0.1, "NONE"))

    # Teacher writes continuously. No checkpoint should be produced for each stroke.
    for index in range(7, 13):
        records.append(record(index, index * 0.1, "LOCAL", score=3.0, changed_ratio=0.01))

    # Teacher stops and the completed writing stays stable.
    for index in range(13, 20):
        records.append(record(index, index * 0.1, "NONE"))

    checkpoints = list(detector.detect(records))

    assert [item.reason for item in checkpoints] == [
        TeachingStateReason.INITIAL_STABLE,
        TeachingStateReason.STABLE_AFTER_CHANGE,
    ]
    assert checkpoints[1].activity_pair_count_since_previous == 6
    assert checkpoints[1].frame_index >= 18


def test_short_pause_is_protected_before_scene_transition() -> None:
    detector = TeachingStateDetector(
        TeachingStateConfig(
            stable_seconds=1.0,
            transition_protection_seconds=0.3,
            minimum_checkpoint_gap_seconds=0.2,
            strong_transition_score=30.0,
        )
    )
    records = [
        record(1, 0.1, "LOCAL", score=4.0, changed_ratio=0.01),
        record(2, 0.2, "LOCAL", score=5.0, changed_ratio=0.02),
        record(3, 0.3, "NONE"),
        record(4, 0.4, "NONE"),
        record(5, 0.5, "NONE"),
        record(6, 0.6, "NONE"),
        record(7, 0.7, "SCENE", score=80.0, changed_ratio=0.7),
        record(8, 0.8, "NONE"),
    ]

    checkpoints = list(detector.detect(records))

    assert checkpoints[0].reason == TeachingStateReason.PRE_TRANSITION_PROTECTION
    assert checkpoints[0].frame_index == 6
    assert checkpoints[0].protected_before_transition is True


def test_unfinished_end_content_gets_fallback_checkpoint() -> None:
    detector = TeachingStateDetector(TeachingStateConfig(stable_seconds=1.0, minimum_checkpoint_gap_seconds=0.2))
    records = [
        record(1, 0.1, "LOCAL", score=2.0, changed_ratio=0.01),
        record(2, 0.2, "LOCAL", score=3.0, changed_ratio=0.01),
        record(3, 0.3, "STRUCTURAL", score=20.0, changed_ratio=0.08),
    ]

    checkpoints = list(detector.detect(records))

    assert len(checkpoints) == 1
    assert checkpoints[0].reason == TeachingStateReason.END_OF_VIDEO_FALLBACK
    assert checkpoints[0].frame_index == 3
