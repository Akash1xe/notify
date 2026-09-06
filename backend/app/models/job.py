from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class JobType(str, Enum):
    PREPARATION = "PREPARATION"
    FRAME_TIMELINE = "FRAME_TIMELINE"
    VISUAL_CHANGE = "VISUAL_CHANGE"
    TEACHING_STATE = "TEACHING_STATE"
    SCREENSHOT_CANDIDATE = "SCREENSHOT_CANDIDATE"
    TRANSCRIPTION = "TRANSCRIPTION"
    TOPIC_DETECTION = "TOPIC_DETECTION"
    OCR_ENRICHMENT = "OCR_ENRICHMENT"
    COVERAGE_AUDIT = "COVERAGE_AUDIT"
    PDF_GENERATION = "PDF_GENERATION"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    MERGING = "MERGING"
    VERIFYING = "VERIFYING"
    FINALIZING = "FINALIZING"
    SCANNING_FRAMES = "SCANNING_FRAMES"
    COMPARING_FRAMES = "COMPARING_FRAMES"
    DETECTING_STATES = "DETECTING_STATES"
    EXTRACTING_SCREENSHOTS = "EXTRACTING_SCREENSHOTS"
    EXTRACTING_AUDIO = "EXTRACTING_AUDIO"
    TRANSCRIBING = "TRANSCRIBING"
    ALIGNING_TRANSCRIPT = "ALIGNING_TRANSCRIPT"
    DETECTING_TOPICS = "DETECTING_TOPICS"
    EXTRACTING_TEXT = "EXTRACTING_TEXT"
    ENRICHING_CONTENT = "ENRICHING_CONTENT"
    VERIFYING_COVERAGE = "VERIFYING_COVERAGE"
    GENERATING_PDF = "GENERATING_PDF"
    READY = "READY"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    CANCELLED = "CANCELLED"

    @property
    def terminal(self) -> bool:
        return self in {self.READY, self.FAILED, self.INTERRUPTED, self.CANCELLED}

    @property
    def transient(self) -> bool:
        return not self.terminal


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JobRecord:
    job_id: str
    video_id: str
    status: JobStatus
    progress: float
    message: str
    created_at: str
    updated_at: str
    job_type: JobType = JobType.PREPARATION
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["job_type"] = self.job_type.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRecord":
        return cls(
            job_id=str(data["job_id"]),
            video_id=str(data["video_id"]),
            status=JobStatus(str(data["status"])),
            progress=float(data.get("progress", 0)),
            message=str(data.get("message", "")),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            job_type=JobType(str(data.get("job_type") or JobType.PREPARATION.value)),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
        )
