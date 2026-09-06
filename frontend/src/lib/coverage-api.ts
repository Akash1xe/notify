import { ApiError } from "@/lib/api";
import type { CoverageJobResponse, CoverageResultResponse, StartCoverageAuditResponse } from "@/types/coverage";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function coverageFetch<T>(path: string, init?: RequestInit, timeoutMs = 30_000): Promise<T> {
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
    if (raw) {
      try { data = JSON.parse(raw); } catch { data = null; }
    }
    if (!response.ok) {
      const shaped = data as { error?: { code?: string; message?: string } } | null;
      throw new ApiError(
        shaped?.error?.code ?? "REQUEST_FAILED",
        shaped?.error?.message ?? "Coverage verification returned an error.",
        response.status,
      );
    }
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("REQUEST_TIMEOUT", "Coverage verification took too long to respond.", 408);
    }
    throw new ApiError("BACKEND_UNAVAILABLE", "Unable to reach the local processing service.", 0);
  } finally {
    window.clearTimeout(timeout);
  }
}

export const coverageApi = {
  start: (videoId: string) => coverageFetch<StartCoverageAuditResponse>(
    "/api/analysis/coverage/start",
    { method: "POST", body: JSON.stringify({ video_id: videoId }) },
  ),
  job: (jobId: string) => coverageFetch<CoverageJobResponse>(
    `/api/analysis/coverage/jobs/${encodeURIComponent(jobId)}`,
    undefined,
    10_000,
  ),
  result: (videoId: string) => coverageFetch<CoverageResultResponse>(
    `/api/analysis/${encodeURIComponent(videoId)}/coverage`,
    undefined,
    15_000,
  ),
};
