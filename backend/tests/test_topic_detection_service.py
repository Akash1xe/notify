import json

from app.services.storage_service import StorageService
from app.services.topic_detection_service import TopicDetectionService


class FakeTranscription:
    def __init__(self, transcript_generated_at="transcript-v1", alignment_generated_at="alignment-v1"):
        self.transcript_generated_at = transcript_generated_at
        self.alignment_generated_at = alignment_generated_at

    def get_result(self, video_id: str):
        return {
            "transcript": {
                "video_id": video_id,
                "status": "READY",
                "segment_count": 8,
                "duration_seconds": 120.0,
                "generated_at": self.transcript_generated_at,
            },
            "alignment": {
                "video_id": video_id,
                "status": "READY",
                "trusted_screenshot_count": 3,
                "generated_at": self.alignment_generated_at,
            },
        }


class FakeReview:
    def __init__(self, generated_at="trusted-v1"):
        self.generated_at = generated_at

    def get_review(self, video_id: str):
        return {
            "summary": {
                "video_id": video_id,
                "selected_count": 3,
                "generated_at": self.generated_at,
            },
            "candidates": [],
        }


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def seed_topic_inputs(storage: StorageService, video_id: str) -> None:
    segments = [
        {"segment_index": 0, "start_seconds": 0.0, "end_seconds": 10.0, "text": "Binary search works on a sorted array."},
        {"segment_index": 1, "start_seconds": 12.0, "end_seconds": 22.0, "text": "We maintain low and high boundaries for the search space."},
        {"segment_index": 2, "start_seconds": 24.0, "end_seconds": 34.0, "text": "The middle index divides the current search space."},
        {"segment_index": 3, "start_seconds": 36.0, "end_seconds": 46.0, "text": "Compare the middle value with the target element."},
        {"segment_index": 4, "start_seconds": 48.0, "end_seconds": 58.0, "text": "Move low or high after the comparison."},
        {"segment_index": 5, "start_seconds": 61.0, "end_seconds": 72.0, "text": "Next let us discuss time complexity and logarithmic growth."},
        {"segment_index": 6, "start_seconds": 74.0, "end_seconds": 88.0, "text": "Each iteration removes half of the remaining elements."},
        {"segment_index": 7, "start_seconds": 90.0, "end_seconds": 110.0, "text": "Therefore binary search has logarithmic time complexity."},
    ]
    write_jsonl(storage.transcript_segments_path(video_id), segments)

    trusted = [
        {"trusted_index": 0, "candidate_index": 0, "frame_index": 200, "timestamp_seconds": 20.0},
        {"trusted_index": 1, "candidate_index": 1, "frame_index": 600, "timestamp_seconds": 62.0},
        {"trusted_index": 2, "candidate_index": 2, "frame_index": 900, "timestamp_seconds": 95.0},
    ]
    write_jsonl(storage.analysis_dir(video_id) / "trusted-screenshots.jsonl", trusted)

    alignment = [
        {"trusted_index": 0, "candidate_index": 0, "frame_index": 200, "timestamp_seconds": 20.0, "text": "search space"},
        {"trusted_index": 1, "candidate_index": 1, "frame_index": 600, "timestamp_seconds": 62.0, "text": "time complexity"},
        {"trusted_index": 2, "candidate_index": 2, "frame_index": 900, "timestamp_seconds": 95.0, "text": "logarithmic"},
    ]
    write_jsonl(storage.screenshot_transcript_map_path(video_id), alignment)

    candidates = [
        {"candidate_index": 0, "source_change_kind": "LOCAL", "reason": "STABLE_AFTER_CHANGE"},
        {"candidate_index": 1, "source_change_kind": "SCENE", "reason": "STABLE_AFTER_CHANGE"},
        {"candidate_index": 2, "source_change_kind": "LOCAL", "reason": "STABLE_AFTER_CHANGE"},
    ]
    write_jsonl(storage.screenshot_candidates_path(video_id), candidates)


def test_detects_sections_and_assigns_every_trusted_screenshot(tmp_path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    video_id = "abcdefghijk"
    seed_topic_inputs(storage, video_id)

    service = TopicDetectionService(storage, FakeTranscription(), FakeReview())
    events = []
    result = service.process(video_id, lambda progress, message: events.append((progress, message)))

    assert result["summary"]["topic_count"] >= 2
    assert result["summary"]["coverage_complete"] is True
    assert result["summary"]["assigned_screenshot_count"] == 3
    assert sum(topic["screenshot_count"] for topic in result["topics"]) == 3
    assert any(1 in topic["trusted_screenshot_indexes"] for topic in result["topics"])
    assert any("complexity" in topic["title"].lower() or "complexity" in topic["keywords"] for topic in result["topics"])
    assert events[-1][0] == 100.0
    assert service.get_result(video_id) is not None


def test_trusted_set_change_invalidates_topics_without_touching_transcript(tmp_path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    video_id = "abcdefghijk"
    seed_topic_inputs(storage, video_id)

    transcription = FakeTranscription()
    review = FakeReview("trusted-v1")
    service = TopicDetectionService(storage, transcription, review)
    service.process(video_id, lambda _progress, _message: None)
    assert service.get_result(video_id) is not None

    review.generated_at = "trusted-v2"
    assert service.get_result(video_id) is None
    assert transcription.transcript_generated_at == "transcript-v1"


def test_first_topic_includes_trusted_visual_before_first_spoken_segment(tmp_path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    service = TopicDetectionService(storage, FakeTranscription(), FakeReview())

    segments = [
        {"segment_index": 0, "start_seconds": 5.0, "end_seconds": 15.0, "text": "Binary search introduction starts here."},
        {"segment_index": 1, "start_seconds": 17.0, "end_seconds": 28.0, "text": "We define the low and high search boundaries."},
    ]
    trusted = [
        {"trusted_index": 0, "candidate_index": 0, "frame_index": 10, "timestamp_seconds": 1.0},
        {"trusted_index": 1, "candidate_index": 1, "frame_index": 200, "timestamp_seconds": 20.0},
    ]

    topics = service._build_topics(segments, trusted, [], 30.0)

    assert topics[0]["start_seconds"] == 1.0
    assert topics[0]["trusted_screenshot_indexes"] == [0, 1]
    assert topics[0]["screenshot_count"] == 2
