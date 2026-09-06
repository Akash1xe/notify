import json
from types import SimpleNamespace

import cv2
import numpy as np

from app.services.screenshot_candidate_service import ScreenshotCandidateService
from app.services.storage_service import StorageService


class FakePrepared:
    def __init__(self, video_path):
        self.video_path = video_path

    def get_prepared_video(self, video_id: str):
        return SimpleNamespace(local_video_path=self.video_path)


class FakeStates:
    def __init__(self, summary: dict):
        self.summary = summary

    def get_summary(self, video_id: str):
        return self.summary


class FakeCapture:
    def __init__(self, frames):
        self.frames = [frame.copy() for frame in frames]
        self.index = 0

    def isOpened(self) -> bool:
        return True

    def set(self, prop, value):
        if prop == cv2.CAP_PROP_POS_FRAMES:
            self.index = int(value)
            return True
        if prop == cv2.CAP_PROP_POS_MSEC:
            return True
        return False

    def read(self):
        if self.index >= len(self.frames):
            return False, None
        frame = self.frames[self.index]
        self.index += 1
        return True, frame

    def release(self) -> None:
        pass


def test_scan_drops_normal_duplicate_but_keeps_protected_duplicate(tmp_path, monkeypatch) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    video_id = "abcdefghijk"
    storage.video_dir(video_id).mkdir(parents=True, exist_ok=True)
    video_path = storage.prepared_video_path(video_id)
    video_path.write_bytes(b"fake-video-for-stat-validation")
    states_summary = {"video_id": video_id, "checkpoint_count": 3, "generated_at": "2026-09-06T00:00:00+00:00"}
    state_records = [
        {"checkpoint_index": 0, "frame_index": 0, "timestamp_seconds": 0.0, "reason": "INITIAL_STABLE", "protected_before_transition": False},
        {"checkpoint_index": 1, "frame_index": 1, "timestamp_seconds": 1.0, "reason": "STABLE_AFTER_CHANGE", "protected_before_transition": False},
        {"checkpoint_index": 2, "frame_index": 2, "timestamp_seconds": 2.0, "reason": "PRE_TRANSITION_PROTECTION", "protected_before_transition": True},
    ]
    states_path = storage.teaching_states_path(video_id)
    states_path.parent.mkdir(parents=True, exist_ok=True)
    states_path.write_text("".join(json.dumps(item) + "\n" for item in state_records), encoding="utf-8")

    frame = np.full((100, 160, 3), 235, dtype=np.uint8)
    frame[20:75, 60:65] = 10
    frames = [frame, frame.copy(), frame.copy()]
    monkeypatch.setattr("app.services.screenshot_candidate_service.cv2.VideoCapture", lambda _: FakeCapture(frames))
    service = ScreenshotCandidateService(storage=storage, prepared=FakePrepared(video_path), states=FakeStates(states_summary))
    summary = service.scan(video_id, lambda _progress, _message: None)

    assert summary["source_checkpoint_count"] == 3
    assert summary["kept_candidate_count"] == 2
    assert summary["duplicate_candidate_count"] == 1
    assert summary["protected_kept_count"] == 1
    assert summary["extraction_mode"] == "RANDOM_ACCESS_CHECKPOINTS"
    manifest = [json.loads(line) for line in storage.screenshot_candidates_path(video_id).read_text(encoding="utf-8").splitlines() if line]
    assert manifest[0]["kept"] is True
    assert manifest[1]["kept"] is False
    assert manifest[1]["duplicate_of_candidate_index"] == 0
    assert manifest[2]["kept"] is True
    assert manifest[2]["protected"] is True
    images = sorted(storage.screenshot_candidates_dir(video_id).glob("*.jpg"))
    assert [path.name for path in images] == ["candidate-000000.jpg", "candidate-000002.jpg"]
    assert service.get_summary(video_id) is not None
