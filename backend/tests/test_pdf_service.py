from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.errors import AppError, ErrorCode
from app.models.job import JobRecord, JobStatus, JobType, utc_now_iso
from app.services.pdf_job_manager import PdfGenerationJobManager
from app.services.pdf_service import PdfService
from app.services.storage_service import StorageService

VIDEO_ID = "abcdefghijk"


class StubCoverage:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready

    def get_result(self, video_id: str):
        return {
            "summary": {
                "video_id": video_id,
                "ready_for_pdf": self.ready,
                "coverage_passed": self.ready,
                "generated_at": "coverage-v1",
            },
            "findings": [],
        }


class StubReview:
    def get_review(self, video_id: str):
        return {
            "summary": {
                "video_id": video_id,
                "selected_count": 3,
                "generated_at": "trusted-v1",
            },
            "candidates": [],
        }


class StubTopics:
    def get_result(self, video_id: str):
        return {
            "summary": {
                "video_id": video_id,
                "topic_count": 2,
                "generated_at": "topics-v1",
            },
            "topics": [
                {
                    "topic_index": 0,
                    "title": "Foundations",
                    "start_seconds": 0.0,
                    "end_seconds": 20.0,
                    "trusted_screenshot_indexes": [0, 1],
                },
                {
                    "topic_index": 1,
                    "title": "Complexity",
                    "start_seconds": 20.0,
                    "end_seconds": 40.0,
                    "trusted_screenshot_indexes": [2],
                },
            ],
        }


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def build_storage(tmp_path: Path) -> StorageService:
    storage = StorageService(
        downloads_dir=tmp_path / "downloads",
        temp_dir=tmp_path / "temp",
        output_dir=tmp_path / "output",
    )
    storage.initialize()
    return storage


def build_service(tmp_path: Path, ready: bool = True) -> PdfService:
    storage = build_storage(tmp_path)
    storage.write_video_manifest(
        VIDEO_ID,
        {
            "title": "Binary Search Complete Tutorial",
            "channel": "Example Teacher",
            "duration_seconds": 40.0,
        },
    )

    analysis = storage.analysis_dir(VIDEO_ID)
    trusted_dir = analysis / "trusted-screenshots"
    trusted_dir.mkdir(parents=True, exist_ok=True)
    trusted_records: list[dict] = []
    content_records: list[dict] = []
    for index, timestamp in enumerate((5.0, 15.0, 30.0)):
        filename = f"trusted-{index:06d}.jpg"
        image = np.full((360, 640, 3), 245, dtype=np.uint8)
        cv2.putText(image, f"SCREENSHOT {index + 1}", (50, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (30, 30, 30), 2)
        assert cv2.imwrite(str(trusted_dir / filename), image)
        trusted_records.append(
            {
                "trusted_index": index,
                "candidate_index": index,
                "frame_index": index * 30,
                "timestamp_seconds": timestamp,
                "reason": "STABLE_AFTER_CHANGE",
                "auto_protected": index == 1,
                "content_loss_risk": index == 1,
                "image_filename": filename,
            }
        )
        content_records.append(
            {
                "trusted_index": index,
                "combined_context": f"Visible lecture context for screenshot {index + 1}",
            }
        )
    write_jsonl(analysis / "trusted-screenshots.jsonl", trusted_records)
    write_jsonl(analysis / "screenshot-content.jsonl", content_records)

    return PdfService(
        storage=storage,
        coverage=StubCoverage(ready=ready),
        review=StubReview(),
        topics=StubTopics(),
    )


def test_pdf_generation_requires_passed_coverage(tmp_path: Path) -> None:
    service = build_service(tmp_path, ready=False)
    with pytest.raises(AppError) as exc:
        service.get_review(VIDEO_ID)
    assert exc.value.code == ErrorCode.COVERAGE_BLOCKED


def test_pdf_review_covers_every_trusted_screenshot(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    review = service.get_review(VIDEO_ID)
    assert [item["trusted_index"] for item in review["items"]] == [0, 1, 2]
    assert review["summary"]["screenshot_count"] == 3

    with pytest.raises(AppError) as exc:
        service.update_review(VIDEO_ID, [0, 2])
    assert exc.value.code == ErrorCode.PDF_REVIEW_INVALID


def test_pdf_generation_is_real_and_order_changes_invalidate_it(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.update_review(VIDEO_ID, [2, 0, 1])
    result = service.generate(
        VIDEO_ID,
        {
            "image_quality": 92,
            "include_cover": True,
            "include_topic_dividers": True,
            "include_context": True,
        },
        lambda _progress, _message: None,
    )

    pdf_path, current = service.download_path(VIDEO_ID)
    assert current == result
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF-")
    assert result["screenshot_count"] == 3
    assert result["topic_count"] == 2
    assert result["page_count"] == 1 + 2 + 3

    service.update_review(VIDEO_ID, [0, 1, 2])
    assert service.get_result(VIDEO_ID) is None


def test_same_review_order_does_not_invalidate_pdf(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.generate(VIDEO_ID, None, lambda _progress, _message: None)
    before = service.get_result(VIDEO_ID)
    assert before is not None
    service.update_review(VIDEO_ID, [0, 1, 2])
    assert service.get_result(VIDEO_ID) is not None


def test_recovered_pdf_job_gets_pdf_specific_interruption_message(tmp_path: Path) -> None:
    storage = build_storage(tmp_path)
    now = utc_now_iso()
    job = JobRecord(
        job_id="job_" + "a" * 32,
        video_id=VIDEO_ID,
        status=JobStatus.INTERRUPTED,
        progress=35.0,
        message="This job was interrupted before completion.",
        created_at=now,
        updated_at=now,
        job_type=JobType.PDF_GENERATION,
        error_code=ErrorCode.PREPARATION_INTERRUPTED,
        error_message="Video preparation was interrupted. Retry the preparation.",
    )
    storage.create_job_workspace(job.job_id)
    storage.write_job(job)

    manager = PdfGenerationJobManager(storage=storage, pdf=object())  # type: ignore[arg-type]
    recovered = manager.get(job.job_id)

    assert recovered.status == JobStatus.INTERRUPTED
    assert recovered.error_code == ErrorCode.ANALYSIS_INTERRUPTED
    assert "PDF generation was interrupted" in recovered.error_message
