from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.models.job import JobStatus


class StartCoverageAuditRequest(BaseModel):
    video_id: str


class StartCoverageAuditResponse(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
    reused_existing: bool
    message: str


class CoverageFinding(BaseModel):
    finding_index: int
    severity: str
    blocking: bool
    start_seconds: float
    end_seconds: float
    reasons: list[str]
    evidence: dict[str, Any]
    rechecked: bool


class CoverageSummary(BaseModel):
    video_id: str
    status: str
    pipeline_version: int
    coverage_passed: bool
    ready_for_pdf: bool
    pdf_status: str | None = None
    finding_count: int
    blocking_finding_count: int
    review_finding_count: int = 0
    high_severity_count: int
    medium_severity_count: int
    warning_count: int
    rechecked_window_count: int
    trusted_screenshot_count: int
    topic_count: int
    visual_pair_count: int
    ocr_record_count: int
    audit_config: dict[str, float]
    source_versions: dict[str, str | None]
    generated_at: str


class CoverageResultResponse(BaseModel):
    status: str = "ready"
    summary: CoverageSummary
    findings: list[CoverageFinding]
