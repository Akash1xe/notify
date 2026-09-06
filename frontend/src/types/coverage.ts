export type CoverageJobStatus =
  | "QUEUED"
  | "VERIFYING_COVERAGE"
  | "READY"
  | "FAILED"
  | "INTERRUPTED"
  | "CANCELLED";

export interface StartCoverageAuditResponse {
  job_id: string;
  video_id: string;
  status: CoverageJobStatus;
  reused_existing: boolean;
  message: string;
}

export interface CoverageJobResponse {
  job_id: string;
  video_id: string;
  job_type: "COVERAGE_AUDIT";
  status: CoverageJobStatus;
  progress: number;
  message: string;
  error: { code: string; message: string } | null;
}

export interface CoverageFinding {
  finding_index: number;
  severity: "HIGH" | "MEDIUM" | "REVIEW" | "WARNING" | string;
  blocking: boolean;
  start_seconds: number;
  end_seconds: number;
  reasons: string[];
  evidence: Record<string, unknown>;
  rechecked: boolean;
}

export interface CoverageSummary {
  video_id: string;
  status: string;
  pipeline_version: number;
  coverage_passed: boolean;
  ready_for_pdf: boolean;
  pdf_status?: "READY" | "REVIEW" | "BLOCKED" | string;
  finding_count: number;
  blocking_finding_count: number;
  review_finding_count: number;
  high_severity_count: number;
  medium_severity_count: number;
  warning_count: number;
  rechecked_window_count: number;
  trusted_screenshot_count: number;
  topic_count: number;
  visual_pair_count: number;
  ocr_record_count: number;
  audit_config: Record<string, number>;
  source_versions: Record<string, string | null>;
  generated_at: string;
}

export interface CoverageResultResponse {
  status: "ready";
  summary: CoverageSummary;
  findings: CoverageFinding[];
}
