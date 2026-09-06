import json

from app.services.coverage_service import CoverageService
from app.services.storage_service import StorageService


class FakeVisualChanges:
    def __init__(self, generated_at="changes-v1"):
        self.generated_at = generated_at

    def get_summary(self, _video_id: str):
        return {"generated_at": self.generated_at, "compared_pair_count": 5, "status": "READY"}


class FakeReview:
    def __init__(self, generated_at="trusted-v1", selected_count=2):
        self.generated_at = generated_at
        self.selected_count = selected_count

    def get_review(self, _video_id: str):
        return {"summary": {"generated_at": self.generated_at, "selected_count": self.selected_count}, "candidates": []}


class FakeTopics:
    def __init__(self, topics=None, generated_at="topics-v1"):
        self.generated_at = generated_at
        self.topic_records = topics or [
            {"topic_index": 0, "title": "Search space", "start_seconds": 0.0, "end_seconds": 40.0, "segment_count": 2, "word_count": 25, "screenshot_count": 1},
            {"topic_index": 1, "title": "Complexity", "start_seconds": 40.0, "end_seconds": 80.0, "segment_count": 2, "word_count": 20, "screenshot_count": 1},
        ]

    def get_result(self, _video_id: str):
        return {"summary": {"generated_at": self.generated_at}, "topics": self.topic_records}


class FakeOcr:
    def __init__(self, ocr_generated_at="ocr-v1", content_generated_at="content-v1"):
        self.ocr_generated_at = ocr_generated_at
        self.content_generated_at = content_generated_at

    def get_result(self, _video_id: str):
        return {
            "ocr": {"generated_at": self.ocr_generated_at},
            "content": {"generated_at": self.content_generated_at},
            "topics": [],
        }


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def seed_inputs(storage: StorageService, video_id: str, *, strong_gap=False, uncertain_ocr=False):
    changes = [
        {"previous_frame_index": 0, "frame_index": 1, "previous_timestamp_seconds": 9.9, "timestamp_seconds": 10.0, "kind": "STRUCTURAL", "change_score": 42.0},
        {"previous_frame_index": 1, "frame_index": 2, "previous_timestamp_seconds": 19.9, "timestamp_seconds": 20.0, "kind": "LOCAL", "change_score": 8.0},
        {"previous_frame_index": 2, "frame_index": 3, "previous_timestamp_seconds": 34.9, "timestamp_seconds": 35.0, "kind": "SCENE" if strong_gap else "LOCAL", "change_score": 72.0 if strong_gap else 7.0},
        {"previous_frame_index": 3, "frame_index": 4, "previous_timestamp_seconds": 59.9, "timestamp_seconds": 60.0, "kind": "STRUCTURAL", "change_score": 38.0},
        {"previous_frame_index": 4, "frame_index": 5, "previous_timestamp_seconds": 69.9, "timestamp_seconds": 70.0, "kind": "NONE", "change_score": 0.1},
    ]
    write_jsonl(storage.frame_differences_path(video_id), changes)

    states = [
        {"checkpoint_index": 0, "frame_index": 100, "timestamp_seconds": 10.0},
        *([{"checkpoint_index": 1, "frame_index": 350, "timestamp_seconds": 35.0}] if strong_gap else []),
        {"checkpoint_index": 2 if strong_gap else 1, "frame_index": 600, "timestamp_seconds": 60.0},
    ]
    write_jsonl(storage.teaching_states_path(video_id), states)

    candidates = [
        {"candidate_index": 0, "frame_index": 100, "timestamp_seconds": 10.0, "protected": False, "content_loss_risk": False},
        {"candidate_index": 1, "frame_index": 600, "timestamp_seconds": 60.0, "protected": False, "content_loss_risk": False},
    ]
    write_jsonl(storage.screenshot_candidates_path(video_id), candidates)

    trusted = [
        {"trusted_index": 0, "candidate_index": 0, "frame_index": 100, "timestamp_seconds": 10.0, "image_filename": "trusted-000000.jpg"},
        {"trusted_index": 1, "candidate_index": 1, "frame_index": 600, "timestamp_seconds": 60.0, "image_filename": "trusted-000001.jpg"},
    ]
    write_jsonl(storage.analysis_dir(video_id) / "trusted-screenshots.jsonl", trusted)

    transcript = [
        {"segment_index": 0, "start_seconds": 5.0, "end_seconds": 14.0, "text": "Binary search starts with low and high boundaries."},
        {"segment_index": 1, "start_seconds": 48.0, "end_seconds": 58.0, "text": "Now we discuss logarithmic complexity."},
    ]
    write_jsonl(storage.transcript_segments_path(video_id), transcript)

    ocr = [
        {"trusted_index": 0, "has_text": not uncertain_ocr, "low_confidence": False, "mean_confidence": 88.0 if not uncertain_ocr else 0.0, "word_count": 5 if not uncertain_ocr else 0},
        {"trusted_index": 1, "has_text": True, "low_confidence": uncertain_ocr, "mean_confidence": 45.0 if uncertain_ocr else 91.0, "word_count": 4},
    ]
    write_jsonl(storage.analysis_dir(video_id) / "screenshot-ocr.jsonl", ocr)


def make_service(tmp_path, *, topics=None):
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    visual = FakeVisualChanges()
    review = FakeReview()
    topic_service = FakeTopics(topics=topics)
    ocr = FakeOcr()
    service = CoverageService(storage, review, topic_service, ocr, visual)
    return storage, service, visual, review, topic_service, ocr


def test_clean_lecture_passes_coverage_gate(tmp_path):
    storage, service, *_ = make_service(tmp_path)
    video_id = "abcdefghijk"
    seed_inputs(storage, video_id)

    result = service.process(video_id, lambda _progress, _message: None)

    assert result["summary"]["coverage_passed"] is True
    assert result["summary"]["ready_for_pdf"] is True
    assert result["summary"]["blocking_finding_count"] == 0
    assert service.get_result(video_id) is not None


def test_uncaptured_scene_and_stable_state_block_pdf_readiness(tmp_path):
    storage, service, *_ = make_service(tmp_path)
    video_id = "abcdefghijk"
    seed_inputs(storage, video_id, strong_gap=True)

    result = service.process(video_id, lambda _progress, _message: None)

    assert result["summary"]["coverage_passed"] is False
    assert result["summary"]["blocking_finding_count"] >= 1
    assert any("UNCAPTURED_STRONG_VISUAL_CHANGE" in item["reasons"] for item in result["findings"])
    assert any("STABLE_STATE_NOT_IN_TRUSTED_SET" in item["reasons"] for item in result["findings"])


def test_ocr_uncertainty_is_warning_not_deletion_or_blocker(tmp_path):
    storage, service, *_ = make_service(tmp_path)
    video_id = "abcdefghijk"
    seed_inputs(storage, video_id, uncertain_ocr=True)

    result = service.process(video_id, lambda _progress, _message: None)

    assert result["summary"]["coverage_passed"] is True
    assert result["summary"]["warning_count"] == 2
    assert all(item["blocking"] is False for item in result["findings"])
    assert {item["reasons"][0] for item in result["findings"]} == {"OCR_NO_TEXT", "OCR_LOW_CONFIDENCE"}


def test_topic_without_screenshot_blocks_coverage(tmp_path):
    topics = [
        {"topic_index": 0, "title": "Search space", "start_seconds": 0.0, "end_seconds": 40.0, "segment_count": 2, "word_count": 25, "screenshot_count": 1},
        {"topic_index": 1, "title": "Missing visual section", "start_seconds": 40.0, "end_seconds": 80.0, "segment_count": 3, "word_count": 40, "screenshot_count": 0},
    ]
    storage, service, *_ = make_service(tmp_path, topics=topics)
    video_id = "abcdefghijk"
    seed_inputs(storage, video_id)

    result = service.process(video_id, lambda _progress, _message: None)

    assert result["summary"]["coverage_passed"] is False
    assert any(item["reasons"] == ["TOPIC_WITHOUT_TRUSTED_SCREENSHOT"] for item in result["findings"])


def test_upstream_change_invalidates_cached_coverage(tmp_path):
    storage, service, visual, *_ = make_service(tmp_path)
    video_id = "abcdefghijk"
    seed_inputs(storage, video_id)
    service.process(video_id, lambda _progress, _message: None)
    assert service.get_result(video_id) is not None

    visual.generated_at = "changes-v2"
    assert service.get_result(video_id) is None
