import json

from app.services.ocr_service import OcrService
from app.services.storage_service import StorageService


class FakeReview:
    def __init__(self, generated_at: str = "trusted-v1") -> None:
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


class FakeTopics:
    def __init__(self, generated_at: str = "topics-v1", alignment_generated_at: str = "alignment-v1") -> None:
        self.generated_at = generated_at
        self.alignment_generated_at = alignment_generated_at

    def get_result(self, video_id: str):
        return {
            "summary": {
                "video_id": video_id,
                "topic_count": 2,
                "trusted_screenshot_count": 3,
                "alignment_generated_at": self.alignment_generated_at,
                "trusted_generated_at": "trusted-v1",
                "generated_at": self.generated_at,
            },
            "topics": [
                {
                    "topic_index": 0,
                    "title": "Binary Search Basics",
                    "trusted_screenshot_indexes": [0, 1],
                    "screenshot_count": 2,
                },
                {
                    "topic_index": 1,
                    "title": "Time Complexity",
                    "trusted_screenshot_indexes": [2],
                    "screenshot_count": 1,
                },
            ],
        }


class FakeRunner:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, image_path):
        self.calls += 1
        if image_path.name.endswith("000000.jpg"):
            return {
                "text": "Binary Search low high mid",
                "lines": [{"text": "Binary Search low high mid", "confidence": 92.0, "bbox": [0, 0, 100, 20]}],
                "line_count": 1,
                "word_count": 5,
                "mean_confidence": 92.0,
                "has_text": True,
            }
        if image_path.name.endswith("000001.jpg"):
            return {
                "text": "",
                "lines": [],
                "line_count": 0,
                "word_count": 0,
                "mean_confidence": 0.0,
                "has_text": False,
            }
        return {
            "text": "Time Complexity O(log n)",
            "lines": [{"text": "Time Complexity O(log n)", "confidence": 48.0, "bbox": [0, 0, 120, 20]}],
            "line_count": 1,
            "word_count": 4,
            "mean_confidence": 48.0,
            "has_text": True,
        }


def write_jsonl(path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def seed_inputs(storage: StorageService, video_id: str) -> None:
    trusted_dir = storage.analysis_dir(video_id) / "trusted-screenshots"
    trusted_dir.mkdir(parents=True, exist_ok=True)
    trusted = []
    for index, timestamp in enumerate((12.0, 28.0, 72.0)):
        filename = f"trusted-{index:06d}.jpg"
        (trusted_dir / filename).write_bytes(b"fake-image")
        trusted.append(
            {
                "trusted_index": index,
                "candidate_index": index + 4,
                "frame_index": 100 + index * 100,
                "timestamp_seconds": timestamp,
                "image_filename": filename,
            }
        )
    write_jsonl(storage.analysis_dir(video_id) / "trusted-screenshots.jsonl", trusted)

    alignment = [
        {
            "trusted_index": 0,
            "candidate_index": 4,
            "frame_index": 100,
            "timestamp_seconds": 12.0,
            "text": "We keep low and high around the binary search space.",
        },
        {
            "trusted_index": 1,
            "candidate_index": 5,
            "frame_index": 200,
            "timestamp_seconds": 28.0,
            "text": "Now calculate the middle index.",
        },
        {
            "trusted_index": 2,
            "candidate_index": 6,
            "frame_index": 300,
            "timestamp_seconds": 72.0,
            "text": "Binary search runs in logarithmic time complexity.",
        },
    ]
    write_jsonl(storage.screenshot_transcript_map_path(video_id), alignment)


def test_ocr_enrichment_covers_every_trusted_screenshot(tmp_path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    video_id = "abcdefghijk"
    seed_inputs(storage, video_id)

    runner = FakeRunner()
    service = OcrService(
        storage=storage,
        review=FakeReview(),
        topics=FakeTopics(),
        runner=runner,
    )
    events = []
    result = service.process(video_id, lambda stage, progress, message: events.append((stage, progress, message)))

    assert runner.calls == 3
    assert result["ocr"]["processed_screenshot_count"] == 3
    assert result["ocr"]["text_detected_count"] == 2
    assert result["ocr"]["no_text_count"] == 1
    assert result["ocr"]["low_confidence_count"] == 1
    assert result["ocr"]["coverage_complete"] is True
    assert result["content"]["enriched_screenshot_count"] == 3
    assert result["content"]["coverage_complete"] is True
    assert result["topics"][0]["screenshots_with_ocr_text"] == 1
    assert "complexity" in result["topics"][1]["visual_keywords"]
    assert events[-1][0] == "ENRICH"
    assert events[-1][1] == 100.0
    assert service.get_result(video_id) is not None

    content_records = [
        json.loads(line)
        for line in (storage.analysis_dir(video_id) / "screenshot-content.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(content_records) == 3
    assert content_records[1]["coverage_flags"] == ["OCR_NO_TEXT"]
    assert "OCR_LOW_CONFIDENCE" in content_records[2]["coverage_flags"]
    assert content_records[0]["topic_title"] == "Binary Search Basics"


def test_topic_change_reuses_raw_ocr_and_rebuilds_only_enrichment(tmp_path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    video_id = "abcdefghijk"
    seed_inputs(storage, video_id)

    topics = FakeTopics("topics-v1", "alignment-v1")
    runner = FakeRunner()
    service = OcrService(storage=storage, review=FakeReview(), topics=topics, runner=runner)

    first = service.process(video_id, lambda _stage, _progress, _message: None)
    first_ocr_generated_at = first["ocr"]["generated_at"]
    first_content_generated_at = first["content"]["generated_at"]
    assert runner.calls == 3

    topics.generated_at = "topics-v2"
    topics.alignment_generated_at = "alignment-v2"
    second = service.process(video_id, lambda _stage, _progress, _message: None)

    assert runner.calls == 3
    assert second["ocr"]["generated_at"] == first_ocr_generated_at
    assert second["content"]["topics_generated_at"] == "topics-v2"
    assert second["content"]["generated_at"] != first_content_generated_at


def test_trusted_set_change_invalidates_raw_ocr(tmp_path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    video_id = "abcdefghijk"
    seed_inputs(storage, video_id)

    review = FakeReview("trusted-v1")
    runner = FakeRunner()
    service = OcrService(storage=storage, review=review, topics=FakeTopics(), runner=runner)
    service.process(video_id, lambda _stage, _progress, _message: None)
    assert runner.calls == 3

    review.generated_at = "trusted-v2"
    service.process(video_id, lambda _stage, _progress, _message: None)
    assert runner.calls == 6


def test_tesseract_tsv_parser_preserves_lines_and_confidence() -> None:
    payload = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t10\t20\t40\t10\t90.0\tBinary\n"
        "5\t1\t1\t1\t1\t2\t55\t20\t45\t10\t80.0\tSearch\n"
        "5\t1\t1\t1\t2\t1\t10\t40\t30\t10\t70.0\tMid\n"
    )
    result = OcrService._parse_tsv(payload)

    assert result["text"] == "Binary Search\nMid"
    assert result["line_count"] == 2
    assert result["word_count"] == 3
    assert result["mean_confidence"] == 80.0
    assert result["lines"][0]["bbox"] == [10, 20, 90, 10]
