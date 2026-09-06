from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from app.services.frame_timeline_service import FrameTimelineService
from app.services.storage_service import StorageService
from app.services.visual_change_service import VisualChangeService

VIDEO_ID = "abc123xyz00"


def make_video(path: Path, fps: float = 5.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (80, 60))
    assert writer.isOpened()

    frames: list[np.ndarray] = []
    for _ in range(4):
        frames.append(np.zeros((60, 80, 3), dtype=np.uint8))
    for _ in range(4):
        frame = np.zeros((60, 80, 3), dtype=np.uint8)
        frame[20:32, 30:42] = (255, 255, 255)
        frames.append(frame)
    for _ in range(4):
        frames.append(np.full((60, 80, 3), 255, dtype=np.uint8))

    for frame in frames:
        writer.write(frame)
    writer.release()


class FakePreparedService:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get_prepared_video(self, video_id: str):
        assert video_id == VIDEO_ID
        return SimpleNamespace(
            local_video_path=self.path,
            probe=SimpleNamespace(duration_seconds=2.4),
        )


def test_visual_change_scan_covers_every_consecutive_pair(tmp_path: Path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    source = storage.prepared_video_path(VIDEO_ID)
    make_video(source)

    prepared = FakePreparedService(source)
    timeline = FrameTimelineService(storage, prepared)
    timeline_summary = timeline.scan(VIDEO_ID, lambda _pct, _message: None)
    assert timeline_summary["frame_count"] == 12

    changes = VisualChangeService(storage, prepared, timeline)
    summary = changes.scan(VIDEO_ID, lambda _pct, _message: None)

    assert summary["compared_frame_count"] == 12
    assert summary["compared_pair_count"] == 11
    assert summary["coverage_complete"] is True
    assert summary["compared_every_consecutive_pair"] is True
    assert (
        summary["no_change_count"]
        + summary["local_change_count"]
        + summary["structural_change_count"]
        + summary["scene_change_count"]
        == 11
    )
    assert summary["change_pair_count"] >= 2
    assert summary["scene_change_count"] >= 1

    lines = storage.frame_differences_path(VIDEO_ID).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 11
    assert storage.frame_differences_summary_path(VIDEO_ID).exists()
    assert changes.get_summary(VIDEO_ID) == summary
