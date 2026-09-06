export type PdfJobStatus =
  | "QUEUED"
  | "GENERATING_PDF"
  | "READY"
  | "FAILED"
  | "INTERRUPTED"
  | "CANCELLED";

export interface PdfGenerationSettings {
  image_quality: number;
  include_cover: boolean;
  include_topic_dividers: boolean;
  include_context: boolean;
}

export interface StartPdfGenerationResponse {
  job_id: string;
  video_id: string;
  status: PdfJobStatus;
  reused_existing: boolean;
  message: string;
}

export interface PdfJobResponse {
  job_id: string;
  video_id: string;
  job_type: "PDF_GENERATION";
  status: PdfJobStatus;
  progress: number;
  message: string;
  error: { code: string; message: string } | null;
}

export interface PdfReviewItem {
  position: number;
  trusted_index: number;
  candidate_index: number;
  frame_index: number;
  timestamp_seconds: number;
  topic_index: number;
  topic_title: string;
  image_filename: string;
  auto_protected: boolean;
  content_loss_risk: boolean;
}

export interface PdfReviewSummary {
  video_id: string;
  pipeline_version: number;
  screenshot_count: number;
  topic_count: number;
  coverage_generated_at: string;
  trusted_generated_at: string;
  topics_generated_at: string;
  updated_at: string;
}

export interface PdfReviewResponse {
  status: "ready";
  summary: PdfReviewSummary;
  items: PdfReviewItem[];
}

export interface PdfArtifact {
  video_id: string;
  status: string;
  pipeline_version: number;
  file_name: string;
  file_size_bytes: number;
  page_count: number;
  screenshot_count: number;
  topic_count: number;
  settings: PdfGenerationSettings;
  coverage_generated_at: string;
  review_updated_at: string;
  trusted_generated_at: string;
  topics_generated_at: string;
  generated_at: string;
}

export interface PdfResultResponse {
  status: "ready";
  pdf: PdfArtifact;
}
