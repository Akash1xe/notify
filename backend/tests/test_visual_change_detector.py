import numpy as np

from app.services.visual_change_detector import ChangeKind, VisualChangeDetector


def test_detector_distinguishes_none_local_and_scene_changes() -> None:
    detector = VisualChangeDetector()
    base = np.zeros((180, 320, 3), dtype=np.uint8)

    unchanged = detector.compare(detector.signature(base), detector.signature(base.copy()))
    assert unchanged.kind == ChangeKind.NONE
    assert unchanged.change_score == 0

    local_frame = base.copy()
    local_frame[70:95, 140:170] = (255, 255, 255)
    local = detector.compare(detector.signature(base), detector.signature(local_frame))
    assert local.kind == ChangeKind.LOCAL
    assert 0 < local.changed_pixel_ratio < 0.06

    scene_frame = np.full_like(base, 255)
    scene = detector.compare(detector.signature(base), detector.signature(scene_frame))
    assert scene.kind == ChangeKind.SCENE
    assert scene.changed_pixel_ratio > 0.9
    assert scene.change_score > local.change_score


def test_detector_retains_color_only_change() -> None:
    detector = VisualChangeDetector()
    first = np.zeros((180, 320, 3), dtype=np.uint8)
    second = first.copy()
    first[40:120, 80:240] = (0, 0, 255)
    second[40:120, 80:240] = (255, 0, 0)

    metrics = detector.compare(detector.signature(first), detector.signature(second))
    assert metrics.kind != ChangeKind.NONE
    assert metrics.changed_pixel_ratio > 0
