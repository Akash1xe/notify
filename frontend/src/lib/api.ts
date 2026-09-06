import type {
  AnalysisJobResponse,
  ApiErrorShape,
  CandidateReviewResponse,
  CleanupResponse,
  FrameTimelineResponse,
  JobResponse,
  LectureTopicResultResponse,
  MetadataResponse,
  PrepareResponse,
  PreparedStatusResponse,
  ScreenshotCandidateResponse,
  StartFrameAnalysisResponse,
  StartScreenshotCandidateAnalysisResponse,
  StartTeachingStateAnalysisResponse,
  StartTopicDetectionResponse,
  StartTranscriptionResponse,
  StartVisualChangeAnalysisResponse,
  StorageStatus,
  SystemStatus,
  TeachingStateResponse,
  TranscriptResultResponse,
  UpdateCandidateDecisionResponse,
  ValidationResponse,
  VisualChangeResponse,
} from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public readonly code: string, message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string, init?: RequestInit, timeoutMs = 30_000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      signal: controller.signal,
    });
    const raw = await response.text();
    let data: unknown = null;
    if (raw) { try { data = JSON.parse(raw); } catch { data = null; } }
    if (!response.ok) {
      const shaped = data as ApiErrorShape | null;
      throw new ApiError(shaped?.error?.code ?? "REQUEST_FAILED", shaped?.error?.message ?? "The local processing service returned an error.", response.status);
    }
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") throw new ApiError("REQUEST_TIMEOUT", "The local processing service took too long to respond.", 408);
    throw new ApiError("BACKEND_UNAVAILABLE", "Unable to reach the local processing service.", 0);
  } finally { window.clearTimeout(timeout); }
}

export const api = {
  health: () => apiFetch<{ status: string; service: string }>("/health", undefined, 5_000),
  validateVideo: (url: string) => apiFetch<ValidationResponse>("/api/video/validate", { method: "POST", body: JSON.stringify({ url }) }),
  getMetadata: (url: string) => apiFetch<MetadataResponse>("/api/video/metadata", { method: "POST", body: JSON.stringify({ url }) }, 45_000),
  prepareVideo: (url: string, videoId: string) => apiFetch<PrepareResponse>("/api/video/prepare", { method: "POST", body: JSON.stringify({ url, video_id: videoId }) }),
  getJob: (jobId: string) => apiFetch<JobResponse>(`/api/jobs/${encodeURIComponent(jobId)}`, undefined, 10_000),
  startFrameAnalysis: (videoId: string) => apiFetch<StartFrameAnalysisResponse>("/api/analysis/start", { method: "POST", body: JSON.stringify({ video_id: videoId }) }),
  getAnalysisJob: (jobId: string) => apiFetch<AnalysisJobResponse>(`/api/analysis/jobs/${encodeURIComponent(jobId)}`, undefined, 10_000),
  getFrameTimeline: (videoId: string) => apiFetch<FrameTimelineResponse>(`/api/analysis/${encodeURIComponent(videoId)}/timeline`, undefined, 10_000),
  startVisualChangeAnalysis: (videoId: string) => apiFetch<StartVisualChangeAnalysisResponse>("/api/analysis/changes/start", { method: "POST", body: JSON.stringify({ video_id: videoId }) }),
  getVisualChangeJob: (jobId: string) => apiFetch<AnalysisJobResponse>(`/api/analysis/changes/jobs/${encodeURIComponent(jobId)}`, undefined, 10_000),
  getVisualChanges: (videoId: string) => apiFetch<VisualChangeResponse>(`/api/analysis/${encodeURIComponent(videoId)}/changes`, undefined, 10_000),
  startTeachingStateAnalysis: (videoId: string) => apiFetch<StartTeachingStateAnalysisResponse>("/api/analysis/states/start", { method: "POST", body: JSON.stringify({ video_id: videoId }) }),
  getTeachingStateJob: (jobId: string) => apiFetch<AnalysisJobResponse>(`/api/analysis/states/jobs/${encodeURIComponent(jobId)}`, undefined, 10_000),
  getTeachingStates: (videoId: string) => apiFetch<TeachingStateResponse>(`/api/analysis/${encodeURIComponent(videoId)}/states`, undefined, 10_000),
  startScreenshotCandidateAnalysis: (videoId: string) => apiFetch<StartScreenshotCandidateAnalysisResponse>("/api/analysis/candidates/start", { method: "POST", body: JSON.stringify({ video_id: videoId }) }),
  getScreenshotCandidateJob: (jobId: string) => apiFetch<AnalysisJobResponse>(`/api/analysis/candidates/jobs/${encodeURIComponent(jobId)}`, undefined, 10_000),
  getScreenshotCandidates: (videoId: string) => apiFetch<ScreenshotCandidateResponse>(`/api/analysis/${encodeURIComponent(videoId)}/candidates`, undefined, 10_000),
  getCandidateReview: (videoId: string) => apiFetch<CandidateReviewResponse>(`/api/analysis/${encodeURIComponent(videoId)}/candidate-review`, undefined, 60_000),
  updateCandidateDecision: (videoId: string, candidateIndex: number, selected: boolean) => apiFetch<UpdateCandidateDecisionResponse>(`/api/analysis/${encodeURIComponent(videoId)}/candidate-review/${candidateIndex}`, { method: "PUT", body: JSON.stringify({ selected }) }, 60_000),
  candidateImageUrl: (videoId: string, candidateIndex: number) => `${API_URL}/api/analysis/${encodeURIComponent(videoId)}/candidates/${candidateIndex}/image`,
  startTranscription: (videoId: string) => apiFetch<StartTranscriptionResponse>("/api/analysis/transcript/start", { method: "POST", body: JSON.stringify({ video_id: videoId }) }, 30_000),
  getTranscriptionJob: (jobId: string) => apiFetch<AnalysisJobResponse>(`/api/analysis/transcript/jobs/${encodeURIComponent(jobId)}`, undefined, 10_000),
  getTranscriptResult: (videoId: string) => apiFetch<TranscriptResultResponse>(`/api/analysis/${encodeURIComponent(videoId)}/transcript`, undefined, 10_000),
  startTopicDetection: (videoId: string) => apiFetch<StartTopicDetectionResponse>("/api/analysis/topics/start", { method: "POST", body: JSON.stringify({ video_id: videoId }) }, 30_000),
  getTopicDetectionJob: (jobId: string) => apiFetch<AnalysisJobResponse>(`/api/analysis/topics/jobs/${encodeURIComponent(jobId)}`, undefined, 10_000),
  getLectureTopics: (videoId: string) => apiFetch<LectureTopicResultResponse>(`/api/analysis/${encodeURIComponent(videoId)}/topics`, undefined, 10_000),
  getVideoStatus: (videoId: string) => apiFetch<PreparedStatusResponse>(`/api/video/${encodeURIComponent(videoId)}/status`),
  deleteLocalVideo: (videoId: string) => apiFetch<{ status: string; video_id: string }>(`/api/video/${encodeURIComponent(videoId)}/local`, { method: "DELETE" }),
  storageStatus: () => apiFetch<StorageStatus>("/api/storage/status"),
  cleanupStorage: () => apiFetch<CleanupResponse>("/api/storage/cleanup", { method: "POST" }),
  systemStatus: () => apiFetch<SystemStatus>("/api/system/status", undefined, 5_000),
};
