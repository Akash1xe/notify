from types import SimpleNamespace

import pytest

from app.core.errors import AppError, ErrorCode
from app.services.candidate_review_service import CandidateReviewService
from app.services.storage_service import StorageService


class FakeCandidates:
    def __init__(self, summary: dict):
        self.summary = summary

    def get_summary(self, video_id: str):
        return self.summary


class FakePrepared:
    def get_prepared_video(self, video_id: str):
        return SimpleNamespace(local_video_path=None)


def write_manifest(storage: StorageService, video_id: str) -> None:
    path = storage.screenshot_candidates_path(video_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        '{"candidate_index":0,"checkpoint_index":0,"frame_index":10,"timestamp_seconds":1.0,"reason":"STABLE_AFTER_CHANGE","source_change_kind":"LOCAL","protected":false,"kept":true,"image_filename":null,"duplicate_of_candidate_index":null,"duplicate_hash_distance":null,"duplicate_mean_abs_difference":null,"edge_density":0.04,"contrast_std":0.2,"content_loss_risk":false,"content_loss_reason":null}',
        '{"candidate_index":1,"checkpoint_index":1,"frame_index":20,"timestamp_seconds":2.0,"reason":"STABLE_AFTER_CHANGE","source_change_kind":"LOCAL","protected":false,"kept":false,"image_filename":null,"duplicate_of_candidate_index":0,"duplicate_hash_distance":0,"duplicate_mean_abs_difference":0.2,"edge_density":0.04,"contrast_std":0.2,"content_loss_risk":false,"content_loss_reason":null}',
        '{"candidate_index":2,"checkpoint_index":2,"frame_index":30,"timestamp_seconds":3.0,"reason":"STABLE_AFTER_CHANGE","source_change_kind":"SCENE","protected":false,"kept":false,"image_filename":null,"duplicate_of_candidate_index":0,"duplicate_hash_distance":1,"duplicate_mean_abs_difference":0.4,"edge_density":0.03,"contrast_std":0.15,"content_loss_risk":true,"content_loss_reason":"SCENE_REPLACEMENT"}',
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_review_restores_risky_candidate_and_preserves_manual_decisions(tmp_path, monkeypatch) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    video_id = "abcdefghijk"
    storage.video_dir(video_id).mkdir(parents=True, exist_ok=True)
    write_manifest(storage, video_id)

    summary = {
        "video_id": video_id,
        "source_checkpoint_count": 3,
        "generated_at": "2026-09-06T00:00:00+00:00",
    }
    service = CandidateReviewService(storage, FakePrepared(), FakeCandidates(summary))  # type: ignore[arg-type]
    monkeypatch.setattr(service, "_preview_bytes_for_record", lambda _video_id, _record: b"fake-jpeg")

    review = service.get_review(video_id)
    assert review["summary"]["selected_count"] == 2
    assert review["summary"]["restored_suppressed_count"] == 1
    assert review["summary"]["auto_protected_count"] == 1
    assert review["candidates"][0]["selected"] is True
    assert review["candidates"][1]["selected"] is False
    assert review["candidates"][2]["selected"] is True
    assert review["candidates"][2]["auto_protected"] is True

    restored = service.update_decision(video_id, 1, True)
    assert restored["summary"]["selected_count"] == 3
    assert restored["summary"]["manual_keep_count"] == 1
    assert restored["candidate"]["manual_decision"] is True

    suppressed = service.update_decision(video_id, 0, False)
    assert suppressed["summary"]["selected_count"] == 2
    assert suppressed["summary"]["manual_suppress_count"] == 1
    assert suppressed["candidate"]["selected"] is False

    with pytest.raises(AppError) as exc_info:
        service.update_decision(video_id, 2, False)
    assert exc_info.value.code == ErrorCode.PROTECTED_CANDIDATE

    trusted = sorted((storage.analysis_dir(video_id) / "trusted-screenshots").glob("*.jpg"))
    assert len(trusted) == 2
