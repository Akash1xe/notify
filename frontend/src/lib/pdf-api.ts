import { ApiError } from "@/lib/api";
import type {
  PdfGenerationSettings,
  PdfJobResponse,
  PdfResultResponse,
  PdfReviewResponse,
  StartPdfGenerationResponse,
} from "@/types/pdf";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function pdfFetch<T>(path: string, init?: RequestInit, timeoutMs = 30_000): Promise<T> {
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
        shaped?.error?.message ?? "PDF generation returned an error.",
        response.status,
      );
    }
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("REQUEST_TIMEOUT", "The local PDF service took too long to respond.", 408);
    }
    throw new ApiError("BACKEND_UNAVAILABLE", "Unable to reach the local processing service.", 0);
  } finally {
    window.clearTimeout(timeout);
  }
}

export const pdfApi = {
  review: (videoId: string) => pdfFetch<PdfReviewResponse>(
    `/api/pdf/${encodeURIComponent(videoId)}/review`,
    undefined,
    15_000,
  ),
  updateReview: (videoId: string, orderedTrustedIndexes: number[]) => pdfFetch<PdfReviewResponse>(
    `/api/pdf/${encodeURIComponent(videoId)}/review`,
    { method: "PUT", body: JSON.stringify({ ordered_trusted_indexes: orderedTrustedIndexes }) },
    15_000,
  ),
  start: (videoId: string, settings: PdfGenerationSettings) => pdfFetch<StartPdfGenerationResponse>(
    "/api/pdf/start",
    { method: "POST", body: JSON.stringify({ video_id: videoId, settings }) },
    30_000,
  ),
  job: (jobId: string) => pdfFetch<PdfJobResponse>(
    `/api/pdf/jobs/${encodeURIComponent(jobId)}`,
    undefined,
    10_000,
  ),
  result: (videoId: string) => pdfFetch<PdfResultResponse>(
    `/api/pdf/${encodeURIComponent(videoId)}`,
    undefined,
    15_000,
  ),
  previewUrl: (videoId: string) => `${API_URL}/api/pdf/${encodeURIComponent(videoId)}/preview`,
  downloadUrl: (videoId: string) => `${API_URL}/api/pdf/${encodeURIComponent(videoId)}/download`,
};
