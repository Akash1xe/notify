export type JobStatus =
  | "QUEUED"
  | "DOWNLOADING"
  | "MERGING"
  | "VERIFYING"
  | "FINALIZING"
  | "SCANNING_FRAMES"
  | "COMPARING_FRAMES"
  | "DETECTING_STATES"
  | "EXTRACTING_SCREENSHOTS"
  | "EXTRACTING_AUDIO"
  | "TRANSCRIBING"
  | "ALIGNING_TRANSCRIPT"
  | "READY"
  | "FAILED"
  | "INTERRUPTED"
  | "CANCELLED";

export type JobType = "PREPARATION" | "FRAME_TIMELINE" | "VISUAL_CHANGE" | "TEACHING_STATE" | "SCREENSHOT_CANDIDATE" | "TRANSCRIPTION";

export interface ApiErrorShape { error: { code: string; message: string } }
export interface ValidationResponse { status: "valid"; video_id: string; normalized_url: string }
export interface VideoMetadata { video_id: string; title: string; duration_seconds: number; duration_formatted: string; channel: string | null; thumbnail_url: string | null; normalized_url: string; is_live: boolean; resolution: string | null }
export interface MetadataResponse { status: "ready"; video: VideoMetadata }
export interface PrepareResponse { job_id: string; video_id: string; status: JobStatus; reused_existing: boolean; message: string }
export interface JobError { code: string; message: string }
export interface JobResponse { job_id: string; video_id: string; status: JobStatus; progress: number; message: string; error: JobError | null }
export interface StartFrameAnalysisResponse { job_id: string; video_id: string; status: JobStatus; reused_existing: boolean; message: string }
export interface StartVisualChangeAnalysisResponse { job_id: string; video_id: string; status: JobStatus; reused_existing: boolean; message: string }
export interface StartTeachingStateAnalysisResponse { job_id: string; video_id: string; status: JobStatus; reused_existing: boolean; message: string }
export interface StartScreenshotCandidateAnalysisResponse { job_id: string; video_id: string; status: JobStatus; reused_existing: boolean; message: string }
export interface StartTranscriptionResponse { job_id: string; video_id: string; status: JobStatus; reused_existing: boolean; message: string }
export interface AnalysisJobResponse extends JobResponse { job_type: JobType }

export interface FrameTimelineSummary { video_id: string; status: string; frame_count: number; fps: number; width: number; height: number; duration_seconds: number; first_timestamp_seconds: number; last_timestamp_seconds: number; generated_at: string }
export interface FrameTimelineResponse { status: "ready"; timeline: FrameTimelineSummary }
export interface VisualChangeSummary { video_id: string; status: string; compared_frame_count: number; compared_pair_count: number; no_change_count: number; local_change_count: number; structural_change_count: number; scene_change_count: number; change_pair_count: number; average_change_score: number; max_change_score: number; max_change_frame_index: number | null; coverage_complete: boolean; compared_every_consecutive_pair: boolean; detector_config: Record<string, number>; generated_at: string; timeline_generated_at: string }
export interface VisualChangeResponse { status: "ready"; changes: VisualChangeSummary }
export interface TeachingStateSummary { video_id: string; status: string; checkpoint_count: number; initial_stable_count: number; stable_after_change_count: number; pre_transition_protection_count: number; end_of_video_fallback_count: number; single_frame_count: number; first_checkpoint_timestamp_seconds: number; last_checkpoint_timestamp_seconds: number; coverage_complete: boolean; source_pair_count: number; detector_config: Record<string, number>; generated_at: string; timeline_generated_at: string; changes_generated_at: string }
export interface TeachingStateResponse { status: "ready"; states: TeachingStateSummary }

export interface ScreenshotCandidateSummary {
  video_id: string;
  status: string;
  pipeline_version: number;
  source_checkpoint_count: number;
  kept_candidate_count: number;
  duplicate_candidate_count: number;
  protected_kept_count: number;
  content_loss_risk_count: number;
  deduplication_conservative: boolean;
  filter_config: Record<string, number>;
  generated_at: string;
  states_generated_at: string;
}
export interface ScreenshotCandidateResponse { status: "ready"; candidates: ScreenshotCandidateSummary }

export interface CandidateReviewItem {
  candidate_index: number;
  checkpoint_index: number;
  frame_index: number;
  timestamp_seconds: number;
  reason: string;
  source_change_kind: string;
  protected: boolean;
  kept: boolean;
  image_filename: string | null;
  duplicate_of_candidate_index: number | null;
  duplicate_hash_distance: number | null;
  duplicate_mean_abs_difference: number | null;
  edge_density: number;
  contrast_std: number;
  content_loss_risk: boolean;
  content_loss_reason: string | null;
  auto_protected: boolean;
  default_selected: boolean;
  manual_decision: boolean | null;
  selected: boolean;
}

export interface TrustedScreenshotSummary {
  video_id: string;
  status: string;
  candidate_count: number;
  selected_count: number;
  manual_keep_count: number;
  manual_suppress_count: number;
  auto_protected_count: number;
  restored_suppressed_count: number;
  candidates_generated_at: string;
  review_updated_at: string;
  generated_at: string;
}

export interface CandidateReviewResponse { status: "ready"; summary: TrustedScreenshotSummary; candidates: CandidateReviewItem[] }
export interface UpdateCandidateDecisionResponse { status: "ready"; summary: TrustedScreenshotSummary; candidate: CandidateReviewItem }

export interface TranscriptSummary {
  video_id: string;
  status: string;
  model_name: string;
  requested_language: string;
  detected_language: string;
  language_probability: number;
  duration_seconds: number;
  segment_count: number;
  word_count: number;
  audio_sample_rate_hz: number;
  generated_at: string;
}

export interface ScreenshotTranscriptAlignmentSummary {
  video_id: string;
  status: string;
  trusted_screenshot_count: number;
  aligned_screenshot_count: number;
  unaligned_screenshot_count: number;
  context_before_seconds: number;
  context_after_seconds: number;
  transcript_generated_at: string;
  trusted_generated_at: string;
  generated_at: string;
}

export interface TranscriptResultResponse {
  status: "ready";
  transcript: TranscriptSummary;
  alignment: ScreenshotTranscriptAlignmentSummary;
}

export interface PreparedStatusResponse { video_id: string; status: "READY" | "NOT_PREPARED"; prepared: boolean; message: string; resolution?: string | null; duration_seconds?: number | null }
export interface StorageStatus { prepared_video_count: number; downloads_size_bytes: number; temp_size_bytes: number; output_size_bytes: number; free_space_bytes: number }
export interface CleanupResponse { status: "completed"; removed_temp_directories: number; freed_bytes: number }
export interface SystemStatus { backend: boolean; ffmpeg_available: boolean; ffprobe_available: boolean; download_directory_writable: boolean; temp_directory_writable: boolean }
