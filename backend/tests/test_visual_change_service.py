from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from app.services.adaptive_visual_scanner import ANALYSIS_ENGINE_VERSION, AdaptiveVisualConfig
from app.services.frame_timeline_service import FrameTimelineService
from app.services.storage_service import StorageService
from app.services.visual_change_service import VisualChangeService

VIDEO_ID = "abc123xyz00"


def make_video(path: Path, fps: float = 30.0, seconds: float = 6.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (160, 90))
    assert writer.isOpened()
    for index in range(int(fps * seconds)):
        frame = np.zeros((90, 160, 3), dtype=np.uint8)
        t = index / fps
        if 2.0 <= t < 3.0:
            width = min(80, 10 + int((t - 2.0) * 70))
            frame[35:42, 20:20 + width] = 255
        elif 3.0 <= t < 4.5:
            frame[35:42, 20:100] = 255
        elif t >= 4.5:
            frame[:] = 220
        writer.write(frame)
    writer.release()


class FakePreparedService:
    def __init__(self, path: Path, duration: float = 6.0) -> None:
        self.path = path
        self.duration = duration

    def get_prepared_video(self, video_id: str):
        assert video_id == VIDEO_ID
        return SimpleNamespace(local_video_path=self.path, probe=SimpleNamespace(duration_seconds=self.duration))


def test_visual_change_scan_is_adaptive_and_preserves_activity(tmp_path: Path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    source = storage.prepared_video_path(VIDEO_ID)
    make_video(source)
    prepared = FakePreparedService(source)
    timeline = FrameTimelineService(storage, prepared)
    timeline_summary = timeline.scan(VIDEO_ID, lambda _pct, _message: None)
    config = AdaptiveVisualConfig(coarse_fps=4.0, fine_fps=12.0, coarse_width=160, fine_width=320)
    changes = VisualChangeService(storage, prepared, timeline, adaptive_config=config)
    summary = changes.scan(VIDEO_ID, lambda _pct, _message: None)

    assert summary["analysis_engine_version"] == ANALYSIS_ENGINE_VERSION
    assert summary["adaptive_sampling"] is True
    assert summary["source_frame_count"] == timeline_summary["frame_count"]
    assert summary["compared_every_consecutive_pair"] is False
    assert summary["coverage_complete"] is True
    assert summary["coarse_sample_count"] < summary["source_frame_count"]
    assert summary["analyzed_sample_count"] < summary["source_frame_count"]
    assert summary["activity_window_count"] >= 1
    assert summary["change_pair_count"] >= 1
    assert storage.frame_differences_path(VIDEO_ID).exists()
    assert (storage.analysis_dir(VIDEO_ID) / "activity-windows.jsonl").exists()
    assert changes.get_summary(VIDEO_ID) == summary


def test_static_heavy_fixture_avoids_most_source_frames(tmp_path: Path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    source = storage.prepared_video_path(VIDEO_ID)
    source.parent.mkdir(parents=True, exist_ok=True)
    fps = 30.0
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), fps, (160, 90))
    assert writer.isOpened()
    frame = np.zeros((90, 160, 3), dtype=np.uint8)
    frame[30:36, 20:100] = 255
    for _ in range(int(fps * 8.0)):
        writer.write(frame)
    writer.release()

    prepared = FakePreparedService(source, duration=8.0)
    timeline = FrameTimelineService(storage, prepared)
    timeline.scan(VIDEO_ID, lambda _pct, _message: None)
    config = AdaptiveVisualConfig(coarse_fps=4.0, fine_fps=12.0, coarse_width=160, fine_width=320)
    service = VisualChangeService(storage, prepared, timeline, adaptive_config=config)
    summary = service.scan(VIDEO_ID, lambda _pct, _message: None)
    assert summary["activity_window_count"] == 0
    assert summary["estimated_frame_reduction_percent"] >= 70.0
