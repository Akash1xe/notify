from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.models.job import JobRecord, JobStatus, utc_now_iso
from app.services.storage_service import StorageService

VIDEO_ID = "dQw4w9WgXcQ"
JOB_ID = "job_" + "a" * 32


@pytest.fixture
def storage(tmp_path: Path) -> StorageService:
    service = StorageService(tmp_path / "downloads", tmp_path / "temp", tmp_path / "output", temp_retention_hours=1)
    service.initialize()
    return service


def test_safe_video_paths(storage: StorageService) -> None:
    assert storage.prepared_video_path(VIDEO_ID).name == "lecture.mp4"
    with pytest.raises(AppError):
        storage.video_dir("../../escape")


def test_atomic_manifest_round_trip(storage: StorageService) -> None:
    storage.video_dir(VIDEO_ID).mkdir(parents=True)
    storage.write_video_manifest(VIDEO_ID, {
        "title": "Test",
        "duration_seconds": 61,
        "normalized_url": f"https://www.youtube.com/watch?v={VIDEO_ID}",
        "resolution": "720p",
    })
    loaded = storage.read_video_manifest(VIDEO_ID)
    assert loaded is not None
    assert loaded["video_id"] == VIDEO_ID
    assert loaded["status"] == "READY"
    assert not storage.video_manifest_path(VIDEO_ID).with_suffix(".json.tmp").exists()


def test_corrupt_manifest_is_not_trusted(storage: StorageService) -> None:
    directory = storage.video_dir(VIDEO_ID)
    directory.mkdir(parents=True)
    storage.video_manifest_path(VIDEO_ID).write_text("{broken", encoding="utf-8")
    assert storage.read_video_manifest(VIDEO_ID) is None


def test_recover_transient_job(storage: StorageService) -> None:
    now = utc_now_iso()
    job = JobRecord(JOB_ID, VIDEO_ID, JobStatus.DOWNLOADING, 30, "Downloading", now, now)
    storage.create_job_workspace(JOB_ID)
    storage.write_job(job)
    (storage.job_dir(JOB_ID) / "source" / "partial.part").write_bytes(b"partial")

    assert storage.recover_interrupted_jobs() == 1
    recovered = storage.read_job(JOB_ID)
    assert recovered is not None
    assert recovered.status == JobStatus.INTERRUPTED
    assert not (storage.job_dir(JOB_ID) / "source").exists()


def test_cleanup_stale_workspace(storage: StorageService) -> None:
    stale_id = "job_" + "b" * 32
    stale = storage.create_job_workspace(stale_id)
    (stale / "large.tmp").write_bytes(b"x" * 100)
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).timestamp()
    import os
    os.utime(stale, (old, old))

    removed, freed = storage.cleanup_stale([])
    assert removed == 1
    assert freed >= 100
    assert not stale.exists()


def test_delete_prepared_video(storage: StorageService) -> None:
    directory = storage.video_dir(VIDEO_ID)
    directory.mkdir(parents=True)
    (directory / "lecture.mp4").write_bytes(b"video")
    storage.write_video_manifest(VIDEO_ID, {"title": "x", "duration_seconds": 1})
    assert storage.delete_prepared_video(VIDEO_ID) is True
    assert not directory.exists()
