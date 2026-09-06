from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from app.services.frame_timeline_service import FrameTimelineService, TIMELINE_VERSION
from app.services.storage_service import StorageService

VIDEO_ID = "abc123xyz00"


def make_video(path: Path, frame_count: int = 15, fps: float = 5.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (80, 60))
    assert writer.isOpened()
    for index in range(frame_count):
        frame = np.zeros((60, 80, 3), dtype=np.uint8)
        cv2.putText(frame, str(index), (5, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
        writer.write(frame)
    writer.release()


class FakePreparedService:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get_prepared_video(self, video_id: str):
        assert video_id == VIDEO_ID
        return SimpleNamespace(local_video_path=self.path, probe=SimpleNamespace(duration_seconds=3.0))


def test_frame_timeline_uses_metadata_without_full_decode(tmp_path: Path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    source = storage.prepared_video_path(VIDEO_ID)
    make_video(source)
    service = FrameTimelineService(storage, FakePreparedService(source))
    summary = service.scan(VIDEO_ID, lambda _pct, _message: None)

    assert summary["timeline_version"] == TIMELINE_VERSION
    assert summary["timeline_mode"] == "METADATA_ONLY"
    assert summary["decoded_frame_count"] == 0
    assert summary["frame_count"] == 15
    assert summary["width"] == 80
    assert summary["height"] == 60
    assert summary["fps"] > 0
    lines = storage.frame_timeline_path(VIDEO_ID).read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 2
    assert service.get_summary(VIDEO_ID) == summary
