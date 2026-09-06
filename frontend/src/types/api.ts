export type JobStatus =
  | "QUEUED"
  | "DOWNLOADING"
  | "MERGING"
  | "VERIFYING"
  | "FINALIZING"
  | "SCANNING_FRAMES"
  | "READY"
  | "FAILED"
  | "INTERRUPTED"
  | "CANCELLED";

export type JobType = "PREPARATION" | "FRAME_TIMELINE";

export interface ApiErrorShape {
  error: {
    code: string;
    message: string;
  };
}

export interface ValidationResponse {
  status: "valid";
  video_id: string;
  normalized_url: string;
}

export interface VideoMetadata {
  video_id: string;
  title: string;
  duration_seconds: number;
  duration_formatted: string;
  channel: string | null;
  thumbnail_url: string | null;
  normalized_url: string;
  is_live: boolean;
  resolution: string | null;
}

export interface MetadataResponse {
  status: "ready";
  video: VideoMetadata;
}

export interface PrepareResponse {
  job_id: string;
  video_id: string;
  status: JobStatus;
  reused_existing: boolean;
  message: string;
}

export interface JobError {
  code: string;
  message: string;
}

export interface JobResponse {
  job_id: string;
  video_id: string;
  status: JobStatus;
  progress: number;
  message: string;
  error: JobError | null;
}

export interface StartFrameAnalysisResponse {
  job_id: string;
  video_id: string;
  status: JobStatus;
  reused_existing: boolean;
  message: string;
}

export interface AnalysisJobResponse extends JobResponse {
  job_type: JobType;
}

export interface FrameTimelineSummary {
  video_id: string;
  status: string;
  frame_count: number;
  fps: number;
  width: number;
  height: number;
  duration_seconds: number;
  first_timestamp_seconds: number;
  last_timestamp_seconds: number;
  generated_at: string;
}

export interface FrameTimelineResponse {
  status: "ready";
  timeline: FrameTimelineSummary;
}

export interface PreparedStatusResponse {
  video_id: string;
  status: "READY" | "NOT_PREPARED";
  prepared: boolean;
  message: string;
  resolution?: string | null;
  duration_seconds?: number | null;
}

export interface StorageStatus {
  prepared_video_count: number;
  downloads_size_bytes: number;
  temp_size_bytes: number;
  output_size_bytes: number;
  free_space_bytes: number;
}

export interface CleanupResponse {
  status: "completed";
  removed_temp_directories: number;
  freed_bytes: number;
}

export interface SystemStatus {
  backend: boolean;
  ffmpeg_available: boolean;
  ffprobe_available: boolean;
  download_directory_writable: boolean;
  temp_directory_writable: boolean;
}
