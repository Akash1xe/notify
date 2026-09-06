from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from app.services.frame_timeline_service import FrameTimelineService
from app.services.storage_service import StorageService
from app.services.visual_change_service import AdaptiveVisualConfig, VisualChangeService

VIDEO_ID = "abc123xyz00"


def make_video(path: Path, fps: float = 30.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (160, 90))
    assert writer.isOpened()
    for index in range(300):
        frame = np.zeros((90, 160, 3), dtype=np.uint8)
        if 120 <= index < 150:
            width = 10 + (index - 120) * 2
            frame[30:45, 20:min(150, 20 + width)] = (255, 255, 255)
        elif 150 <= index < 210:
            frame[30:45, 20:90] = (255, 255, 255)
        elif index >= 210:
            frame[:] = 255
        writer.write(frame)
    writer.release()


class FakePreparedService:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get_prepared_video(self, video_id: str):
        assert video_id == VIDEO_ID
        return SimpleNamespace(local_video_path=self.path, probe=SimpleNamespace(duration_seconds=10.0))


def test_visual_change_scan_is_adaptive_and_reduces_source_work(tmp_path: Path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    source = storage.prepared_video_path(VIDEO_ID)
    make_video(source)

    prepared = FakePreparedService(source)
    timeline = FrameTimelineService(storage, prepared)
    timeline_summary = timeline.scan(VIDEO_ID, lambda _pct, _message: None)
    assert timeline_summary["frame_count"] >= 290

    changes = VisualChangeService(
        storage,
        prepared,
        timeline,
        config=AdaptiveVisualConfig(coarse_fps=3.0, fine_fps=10.0, coarse_width=128, fine_width=160),
    )
    summary = changes.scan(VIDEO_ID, lambda _pct, _message: None)

    assert summary["adaptive_sampling"] is True
    assert summary["compared_every_consecutive_pair"] is False
    assert summary["coverage_complete"] is True
    assert summary["coarse_sample_count"] > 0
    assert summary["fine_sample_count"] > 0
    assert summary["activity_window_count"] >= 1
    assert summary["analyzed_sample_count"] < summary["source_frame_count"]
    assert summary["estimated_frame_reduction_percent"] > 50
    assert summary["compared_pair_count"] > 0
    assert storage.frame_differences_path(VIDEO_ID).exists()
    assert (storage.analysis_dir(VIDEO_ID) / "activity-windows.jsonl").exists()
    assert changes.get_summary(VIDEO_ID) == summary
