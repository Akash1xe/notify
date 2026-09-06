from __future__ import annotations

from pathlib import Path

from app.models.job import JobStatus
from app.schemas.video import VideoMetadata
from app.services.job_manager import JobManager
from app.services.storage_service import StorageService

VIDEO_ID = "dQw4w9WgXcQ"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


class FakePrepared:
    def get_prepared_video(self, video_id: str):
        return None


class FakeYoutube:
    def metadata(self, url: str) -> VideoMetadata:
        return VideoMetadata(
            video_id=VIDEO_ID,
            title="Lecture",
            duration_seconds=60,
            duration_formatted="1:00",
            normalized_url=URL,
            is_live=False,
        )


class HoldingDownloader:
    def prepare(self, job_id, metadata, callback):
        callback(JobStatus.DOWNLOADING, 10, "Downloading video...")
        return Path("unused")


def test_prepare_creates_job(tmp_path, monkeypatch) -> None:
    storage = StorageService(tmp_path / "d", tmp_path / "t", tmp_path / "o")
    storage.initialize()
    manager = JobManager(storage, FakeYoutube(), HoldingDownloader(), FakePrepared())

    # Avoid racing a real thread: intercept Thread.start and inspect the created state.
    monkeypatch.setattr("threading.Thread.start", lambda self: None)
    response = manager.start_prepare(URL, VIDEO_ID)
    assert response.status == JobStatus.QUEUED
    assert manager.get(response.job_id).video_id == VIDEO_ID


def test_mismatched_video_id_rejected(tmp_path) -> None:
    storage = StorageService(tmp_path / "d", tmp_path / "t", tmp_path / "o")
    storage.initialize()
    manager = JobManager(storage, FakeYoutube(), HoldingDownloader(), FakePrepared())
    import pytest
    with pytest.raises(Exception):
        manager.start_prepare(URL, "aaaaaaaaaaa")
