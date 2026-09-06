import json
from types import SimpleNamespace

from app.services.storage_service import StorageService
from app.services.transcription_service import TranscriptionService


class FakePrepared:
    def __init__(self, video_path):
        self.video_path = video_path

    def get_prepared_video(self, video_id: str):
        return SimpleNamespace(local_video_path=self.video_path)


class FakeMedia:
    def __init__(self):
        self.extract_calls = 0

    def extract_transcription_audio(self, source, destination):
        self.extract_calls += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"RIFF-fake-wave-data")

    def probe(self, source):
        return SimpleNamespace(duration_seconds=30.0)


class FakeReview:
    def __init__(self, generated_at: str = "trusted-v1"):
        self.generated_at = generated_at

    def get_review(self, video_id: str):
        return {
            "summary": {
                "video_id": video_id,
                "selected_count": 2,
                "generated_at": self.generated_at,
            },
            "candidates": [],
        }


class FakeModel:
    def __init__(self):
        self.transcribe_calls = 0

    def transcribe(self, audio_path, **kwargs):
        self.transcribe_calls += 1
        segments = [
            SimpleNamespace(start=0.0, end=5.0, text=" Binary search starts with low and high. "),
            SimpleNamespace(start=8.0, end=14.0, text=" Now calculate the middle index. "),
            SimpleNamespace(start=19.0, end=25.0, text=" Move the left boundary when needed. "),
        ]
        info = SimpleNamespace(duration=30.0, language="en", language_probability=0.99)
        return iter(segments), info


def write_trusted_manifest(storage: StorageService, video_id: str) -> None:
    path = storage.analysis_dir(video_id) / "trusted-screenshots.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "trusted_index": 0,
            "candidate_index": 2,
            "frame_index": 100,
            "timestamp_seconds": 10.0,
            "image_filename": "trusted-000000.jpg",
        },
        {
            "trusted_index": 1,
            "candidate_index": 5,
            "frame_index": 220,
            "timestamp_seconds": 22.0,
            "image_filename": "trusted-000001.jpg",
        },
    ]
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def test_transcription_persists_segments_and_aligns_trusted_screenshots(tmp_path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    video_id = "abcdefghijk"
    video_path = storage.prepared_video_path(video_id)
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fake-prepared-video")
    write_trusted_manifest(storage, video_id)

    media = FakeMedia()
    review = FakeReview()
    model = FakeModel()
    service = TranscriptionService(
        storage=storage,
        prepared=FakePrepared(video_path),
        media=media,
        review=review,
        model_loader=lambda _name, _device, _compute: model,
    )

    events = []
    result = service.process(video_id, lambda stage, progress, message: events.append((stage, progress, message)))

    assert result["transcript"]["segment_count"] == 3
    assert result["transcript"]["word_count"] > 0
    assert result["alignment"]["trusted_screenshot_count"] == 2
    assert result["alignment"]["aligned_screenshot_count"] == 2
    assert media.extract_calls == 1
    assert model.transcribe_calls == 1
    assert storage.transcript_segments_path(video_id).exists()
    assert storage.screenshot_transcript_map_path(video_id).exists()

    mapping = [json.loads(line) for line in storage.screenshot_transcript_map_path(video_id).read_text(encoding="utf-8").splitlines()]
    assert len(mapping) == 2
    assert "middle index" in mapping[0]["text"]
    assert "left boundary" in mapping[1]["text"]
    assert service.get_result(video_id) is not None
    assert events[-1][0] == "ALIGN"
    assert events[-1][1] == 100.0


def test_review_change_realigns_without_rerunning_whisper(tmp_path) -> None:
    storage = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output")
    storage.initialize()
    video_id = "abcdefghijk"
    video_path = storage.prepared_video_path(video_id)
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fake-prepared-video")
    write_trusted_manifest(storage, video_id)

    media = FakeMedia()
    review = FakeReview("trusted-v1")
    model = FakeModel()
    service = TranscriptionService(
        storage=storage,
        prepared=FakePrepared(video_path),
        media=media,
        review=review,
        model_loader=lambda _name, _device, _compute: model,
    )

    first = service.process(video_id, lambda _stage, _progress, _message: None)
    transcript_generated_at = first["transcript"]["generated_at"]
    assert media.extract_calls == 1
    assert model.transcribe_calls == 1

    review.generated_at = "trusted-v2"
    second = service.process(video_id, lambda _stage, _progress, _message: None)

    assert second["transcript"]["generated_at"] == transcript_generated_at
    assert second["alignment"]["trusted_generated_at"] == "trusted-v2"
    assert media.extract_calls == 1
    assert model.transcribe_calls == 1
