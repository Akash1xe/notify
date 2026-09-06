from __future__ import annotations

from pydantic import BaseModel

from app.models.job import JobStatus, JobType


class StartFrameAnalysisRequest(BaseModel):
    video_id: str


class StartFrameAnalysisResponse(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
    reused_existing: bool
    message: str


class StartVisualChangeAnalysisRequest(BaseModel):
    video_id: str


class StartVisualChangeAnalysisResponse(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
    reused_existing: bool
    message: str


class StartTeachingStateAnalysisRequest(BaseModel):
    video_id: str


class StartTeachingStateAnalysisResponse(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
    reused_existing: bool
    message: str


class StartScreenshotCandidateAnalysisRequest(BaseModel):
    video_id: str


class StartScreenshotCandidateAnalysisResponse(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
    reused_existing: bool
    message: str


class StartTranscriptionRequest(BaseModel):
    video_id: str


class StartTranscriptionResponse(BaseModel):
    job_id: str
    video_id: str
    status: JobStatus
    reused_existing: bool
    message: str


class AnalysisJobError(BaseModel):
    code: str
    message: str


class AnalysisJobResponse(BaseModel):
    job_id: str
    video_id: str
    job_type: JobType
    status: JobStatus
    progress: float
    message: str
    error: AnalysisJobError | None = None


class FrameTimelineSummary(BaseModel):
    video_id: str
    status: str
    frame_count: int
    fps: float
    width: int
    height: int
    duration_seconds: float
    first_timestamp_seconds: float
    last_timestamp_seconds: float
    generated_at: str


class FrameTimelineResponse(BaseModel):
    status: str = "ready"
    timeline: FrameTimelineSummary


class VisualChangeSummary(BaseModel):
    video_id: str
    status: str
    compared_frame_count: int
    compared_pair_count: int
    no_change_count: int
    local_change_count: int
    structural_change_count: int
    scene_change_count: int
    change_pair_count: int
    average_change_score: float
    max_change_score: float
    max_change_frame_index: int | None
    coverage_complete: bool
    compared_every_consecutive_pair: bool
    detector_config: dict[str, float | int]
    generated_at: str
    timeline_generated_at: str


class VisualChangeResponse(BaseModel):
    status: str = "ready"
    changes: VisualChangeSummary


class TeachingStateSummary(BaseModel):
    video_id: str
    status: str
    checkpoint_count: int
    initial_stable_count: int
    stable_after_change_count: int
    pre_transition_protection_count: int
    end_of_video_fallback_count: int
    single_frame_count: int
    first_checkpoint_timestamp_seconds: float
    last_checkpoint_timestamp_seconds: float
    coverage_complete: bool
    source_pair_count: int
    detector_config: dict[str, float]
    generated_at: str
    timeline_generated_at: str
    changes_generated_at: str


class TeachingStateResponse(BaseModel):
    status: str = "ready"
    states: TeachingStateSummary


class ScreenshotCandidateSummary(BaseModel):
    video_id: str
    status: str
    pipeline_version: int
    source_checkpoint_count: int
    kept_candidate_count: int
    duplicate_candidate_count: int
    protected_kept_count: int
    content_loss_risk_count: int
    deduplication_conservative: bool
    filter_config: dict[str, float | int]
    generated_at: str
    states_generated_at: str


class ScreenshotCandidateResponse(BaseModel):
    status: str = "ready"
    candidates: ScreenshotCandidateSummary


class CandidateReviewItem(BaseModel):
    candidate_index: int
    checkpoint_index: int
    frame_index: int
    timestamp_seconds: float
    reason: str
    source_change_kind: str
    protected: bool
    kept: bool
    image_filename: str | None = None
    duplicate_of_candidate_index: int | None = None
    duplicate_hash_distance: int | None = None
    duplicate_mean_abs_difference: float | None = None
    edge_density: float
    contrast_std: float
    content_loss_risk: bool
    content_loss_reason: str | None = None
    auto_protected: bool
    default_selected: bool
    manual_decision: bool | None = None
    selected: bool


class TrustedScreenshotSummary(BaseModel):
    video_id: str
    status: str
    candidate_count: int
    selected_count: int
    manual_keep_count: int
    manual_suppress_count: int
    auto_protected_count: int
    restored_suppressed_count: int
    candidates_generated_at: str
    review_updated_at: str
    generated_at: str


class CandidateReviewResponse(BaseModel):
    status: str = "ready"
    summary: TrustedScreenshotSummary
    candidates: list[CandidateReviewItem]


class UpdateCandidateDecisionRequest(BaseModel):
    selected: bool
    force: bool = False


class UpdateCandidateDecisionResponse(BaseModel):
    status: str = "ready"
    summary: TrustedScreenshotSummary
    candidate: CandidateReviewItem


class TranscriptSummary(BaseModel):
    video_id: str
    status: str
    model_name: str
    requested_language: str
    detected_language: str
    language_probability: float
    duration_seconds: float
    segment_count: int
    word_count: int
    audio_sample_rate_hz: int
    generated_at: str


class ScreenshotTranscriptAlignmentSummary(BaseModel):
    video_id: str
    status: str
    trusted_screenshot_count: int
    aligned_screenshot_count: int
    unaligned_screenshot_count: int
    context_before_seconds: float
    context_after_seconds: float
    transcript_generated_at: str
    trusted_generated_at: str
    generated_at: str


class TranscriptResultResponse(BaseModel):
    status: str = "ready"
    transcript: TranscriptSummary
    alignment: ScreenshotTranscriptAlignmentSummary
