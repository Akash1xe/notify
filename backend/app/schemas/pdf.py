from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.job import JobStatus


class PdfGenerationSettings(BaseModel):
    image_quality: int = Field(default=92, ge=70, le=100)
    include_cover: bool = True
    include_topic_dividers: bool = True
    include_context: bool = False


class StartPdfGenerationRequest(BaseModel):
    video_id: str
    settings: PdfGenerationSettings = Field(default_factory=PdfGenerationSettings)


class StartPdfGenerationResponse(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
    reused_existing: bool
    message: str


class PdfReviewItem(BaseModel):
    position: int
    trusted_index: int
    candidate_index: int
    frame_index: int
    timestamp_seconds: float
    topic_index: int
    topic_title: str
    image_filename: str
    auto_protected: bool
    content_loss_risk: bool


class PdfReviewSummary(BaseModel):
    video_id: str
    pipeline_version: int
    screenshot_count: int
    topic_count: int
    coverage_generated_at: str
    trusted_generated_at: str
    topics_generated_at: str
    updated_at: str


class PdfReviewResponse(BaseModel):
    status: str = "ready"
    summary: PdfReviewSummary
    items: list[PdfReviewItem]


class UpdatePdfReviewRequest(BaseModel):
    ordered_trusted_indexes: list[int]


class PdfArtifact(BaseModel):
    video_id: str
    status: str
    pipeline_version: int
    file_name: str
    file_size_bytes: int
    page_count: int
    screenshot_count: int
    topic_count: int
    settings: PdfGenerationSettings
    coverage_generated_at: str
    review_updated_at: str
    trusted_generated_at: str
    topics_generated_at: str
    generated_at: str


class PdfResultResponse(BaseModel):
    status: str = "ready"
    pdf: PdfArtifact
