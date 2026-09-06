import type {
  ApiErrorShape,
  CleanupResponse,
  JobResponse,
  MetadataResponse,
  PrepareResponse,
  PreparedStatusResponse,
  StorageStatus,
  SystemStatus,
  ValidationResponse,
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
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      signal: controller.signal,
    });

    const raw = await response.text();
    let data: unknown = null;
    if (raw) {
      try { data = JSON.parse(raw); } catch { data = null; }
    }

    if (!response.ok) {
      const shaped = data as ApiErrorShape | null;
      const code = shaped?.error?.code ?? "REQUEST_FAILED";
      const message = shaped?.error?.message ?? "The local processing service returned an error.";
      throw new ApiError(code, message, response.status);
    }

    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("REQUEST_TIMEOUT", "The local processing service took too long to respond.", 408);
    }
    throw new ApiError("BACKEND_UNAVAILABLE", "Unable to reach the local processing service.", 0);
  } finally {
    window.clearTimeout(timeout);
  }
}

export const api = {
  health: () => apiFetch<{ status: string; service: string }>("/health", undefined, 5_000),
  validateVideo: (url: string) => apiFetch<ValidationResponse>("/api/video/validate", {
    method: "POST",
    body: JSON.stringify({ url }),
  }),
  getMetadata: (url: string) => apiFetch<MetadataResponse>("/api/video/metadata", {
    method: "POST",
    body: JSON.stringify({ url }),
  }, 45_000),
  prepareVideo: (url: string, videoId: string) => apiFetch<PrepareResponse>("/api/video/prepare", {
    method: "POST",
    body: JSON.stringify({ url, video_id: videoId }),
  }),
  getJob: (jobId: string) => apiFetch<JobResponse>(`/api/jobs/${encodeURIComponent(jobId)}`, undefined, 10_000),
  getVideoStatus: (videoId: string) => apiFetch<PreparedStatusResponse>(`/api/video/${encodeURIComponent(videoId)}/status`),
  deleteLocalVideo: (videoId: string) => apiFetch<{ status: string; video_id: string }>(`/api/video/${encodeURIComponent(videoId)}/local`, { method: "DELETE" }),
  storageStatus: () => apiFetch<StorageStatus>("/api/storage/status"),
  cleanupStorage: () => apiFetch<CleanupResponse>("/api/storage/cleanup", { method: "POST" }),
  systemStatus: () => apiFetch<SystemStatus>("/api/system/status", undefined, 5_000),
};
