import json
from pathlib import Path
from types import SimpleNamespace

from app.services.storage_service import StorageService
from app.services.teaching_state_detector import TeachingStateConfig, TeachingStateDetector
from app.services.teaching_state_service import TeachingStateService

VIDEO_ID = "abc123xyz00"


class FakePreparedService:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get_prepared_video(self, video_id: str):
        assert video_id == VIDEO_ID
        return SimpleNamespace(local_video_path=self.path)


class FakeTimelineService:
    def get_summary(self, video_id: str):
        assert video_id == VIDEO_ID
        return {
            "video_id": VIDEO_ID,
            "frame_count": 10,
            "generated_at": "timeline-v1",
            "first_timestamp_seconds": 0.0,
        }


class FakeChangeService:
    def get_summary(self, video_id: str):
        assert video_id == VIDEO_ID
        return {
            "video_id": VIDEO_ID,
            "compared_pair_count": 9,
            "generated_at": "changes-v1",
        }


def change_record(index: int, kind: str) -> dict:
    timestamp = index * 0.2
    return {
        "previous_frame_index": index - 1,
        "frame_index": index,
        "previous_timestamp_seconds": timestamp - 0.2,
        "timestamp_seconds": timestamp,
        "delta_seconds": 0.2,
        "kind": kind,
        "mean_pixel_delta": 0.0,
        "changed_pixel_ratio": 0.01 if kind != "NONE" else 0.0,
        "edge_change_ratio": 0.0,
        "change_bbox_area_ratio": 0.01,
        "change_score": 3.0 if kind != "NONE" else 0.0,
    }


def test_teaching_states_are_persisted_and_reusable(tmp_path: Path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    source = storage.prepared_video_path(VIDEO_ID)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"prepared-video-placeholder")

    records = [
        change_record(1, "NONE"),
        change_record(2, "NONE"),
        change_record(3, "NONE"),
        change_record(4, "LOCAL"),
        change_record(5, "LOCAL"),
        change_record(6, "NONE"),
        change_record(7, "NONE"),
        change_record(8, "NONE"),
        change_record(9, "NONE"),
    ]
    differences_path = storage.frame_differences_path(VIDEO_ID)
    differences_path.parent.mkdir(parents=True, exist_ok=True)
    differences_path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")

    service = TeachingStateService(
        storage=storage,
        prepared=FakePreparedService(source),
        timeline=FakeTimelineService(),
        changes=FakeChangeService(),
        detector=TeachingStateDetector(TeachingStateConfig(stable_seconds=0.4, minimum_checkpoint_gap_seconds=0.2)),
    )

    events: list[tuple[float, str]] = []
    summary = service.scan(VIDEO_ID, lambda pct, message: events.append((pct, message)))

    assert summary["checkpoint_count"] == 2
    assert summary["coverage_complete"] is True
    assert summary["source_pair_count"] == 9
    assert storage.teaching_states_path(VIDEO_ID).exists()
    assert storage.teaching_states_summary_path(VIDEO_ID).exists()
    assert service.get_summary(VIDEO_ID) == summary

    checkpoints = [json.loads(line) for line in storage.teaching_states_path(VIDEO_ID).read_text(encoding="utf-8").splitlines()]
    assert [item["reason"] for item in checkpoints] == ["INITIAL_STABLE", "STABLE_AFTER_CHANGE"]
    assert checkpoints[1]["frame_index"] > checkpoints[0]["frame_index"]
