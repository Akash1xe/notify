export type CoverageDisposition = "BLOCK" | "REVIEW" | "WARNING";

export type CoverageFinding = {
  finding_index: number;
  severity: string;
  disposition: CoverageDisposition;
  blocking: boolean;
  start_seconds: number;
  end_seconds: number;
  reasons: string[];
  evidence: Record<string, unknown>;
  rechecked: boolean;
};

export type CoverageSummary = {
  video_id: string;
  status: string;
  pipeline_version: number;
  coverage_passed: boolean;
  ready_for_pdf: boolean;
  pdf_gate_status: "READY" | "REVIEW_REQUIRED" | "BLOCKED";
  finding_count: number;
  blocking_finding_count: number;
  hard_blocking_finding_count: number;
  review_required_count: number;
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
};

export type CoverageResultResponse = {
  status: "ready";
  summary: CoverageSummary;
  findings: CoverageFinding[];
};

export type StartCoverageResponse = {
  job_id: string;
  video_id: string;
  status: string;
  reused_existing: boolean;
  message: string;
};
