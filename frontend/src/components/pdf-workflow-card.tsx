"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { pdfApi } from "@/lib/pdf-api";
import type { VideoMetadata } from "@/types/api";
import type {
  PdfArtifact,
  PdfGenerationSettings,
  PdfJobResponse,
  PdfReviewItem,
  PdfReviewResponse,
} from "@/types/pdf";

interface Props {
  video: VideoMetadata;
  onBackToCoverage: () => void;
  onChooseAnother: () => void;
}

type Step = "LOADING" | "REVIEW" | "GENERATING" | "READY" | "ERROR";

const DEFAULT_SETTINGS: PdfGenerationSettings = {
  image_quality: 92,
  include_cover: true,
  include_topic_dividers: true,
  include_context: false,
};

function formatTime(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB"];
  let size = value / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && size >= 1024; index += 1) {
    size /= 1024;
    unit = units[index];
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${unit}`;
}

function readableError(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return "Final PDF generation failed unexpectedly.";
}

export function PdfWorkflowCard({ video, onBackToCoverage, onChooseAnother }: Props) {
  const [step, setStep] = useState<Step>("LOADING");
  const [review, setReview] = useState<PdfReviewResponse | null>(null);
  const [ordered, setOrdered] = useState<PdfReviewItem[]>([]);
  const [settings, setSettings] = useState<PdfGenerationSettings>(DEFAULT_SETTINGS);
  const [job, setJob] = useState<PdfJobResponse | null>(null);
  const [artifact, setArtifact] = useState<PdfArtifact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);

  async function loadReview() {
    setStep("LOADING");
    setError(null);
    try {
      const current = await pdfApi.review(video.video_id);
      setReview(current);
      setOrdered(current.items);
      setStep("REVIEW");
    } catch (reason) {
      setError(readableError(reason));
      setStep("ERROR");
    }
  }

  useEffect(() => {
    void loadReview();
    return () => { generation.current += 1; };
    // video_id uniquely scopes this final workflow.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [video.video_id]);

  const savedOrder = useMemo(
    () => review?.items.map((item) => item.trusted_index).join(",") ?? "",
    [review],
  );
  const currentOrder = useMemo(
    () => ordered.map((item) => item.trusted_index).join(","),
    [ordered],
  );
  const orderChanged = savedOrder !== currentOrder;

  function moveItem(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= ordered.length) return;
    setOrdered((items) => {
      const next = [...items];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    setArtifact(null);
  }

  function resetTopicOrder() {
    setOrdered((items) => [...items].sort((a, b) => {
      if (a.topic_index !== b.topic_index) return a.topic_index - b.topic_index;
      if (a.timestamp_seconds !== b.timestamp_seconds) return a.timestamp_seconds - b.timestamp_seconds;
      return a.trusted_index - b.trusted_index;
    }));
    setArtifact(null);
  }

  async function persistOrder() {
    const updated = await pdfApi.updateReview(video.video_id, ordered.map((item) => item.trusted_index));
    setReview(updated);
    setOrdered(updated.items);
    return updated;
  }

  async function pollJob(jobId: string) {
    const currentGeneration = ++generation.current;
    let failures = 0;
    while (currentGeneration === generation.current) {
      try {
        const current = await pdfApi.job(jobId);
        failures = 0;
        setJob(current);
        if (current.status === "READY") {
          const result = await pdfApi.result(video.video_id);
          setArtifact(result.pdf);
          setStep("READY");
          return;
        }
        if (["FAILED", "INTERRUPTED", "CANCELLED"].includes(current.status)) {
          setError(current.error?.message ?? current.message);
          setStep("ERROR");
          return;
        }
      } catch (reason) {
        failures += 1;
        if (failures >= 3) {
          setError(readableError(reason));
          setStep("ERROR");
          return;
        }
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1250));
    }
  }

  async function generatePdf() {
    generation.current += 1;
    setError(null);
    setArtifact(null);
    setJob(null);
    setStep("GENERATING");
    try {
      await persistOrder();
      const created = await pdfApi.start(video.video_id, settings);
      const initial: PdfJobResponse = {
        job_id: created.job_id,
        video_id: created.video_id,
        job_type: "PDF_GENERATION",
        status: created.status,
        progress: created.status === "READY" ? 100 : 0,
        message: created.message,
        error: null,
      };
      setJob(initial);
      if (created.status === "READY") {
        const result = await pdfApi.result(video.video_id);
        setArtifact(result.pdf);
        setStep("READY");
        return;
      }
      void pollJob(created.job_id);
    } catch (reason) {
      setError(readableError(reason));
      setStep("ERROR");
    }
  }

  if (step === "LOADING") {
    return (
      <section className="rounded-2xl border border-cyan-900/60 bg-cyan-950/20 p-6">
        <p className="text-sm text-cyan-100">Loading the coverage-approved PDF review set...</p>
      </section>
    );
  }

  if (step === "READY" && artifact) {
    return (
      <section className="rounded-2xl border border-emerald-900/60 bg-emerald-950/20 p-6">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">✓ Final PDF ready</p>
        <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

        <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">PDF pages</p><p className="mt-1 font-semibold text-slate-100">{artifact.page_count}</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Screenshots</p><p className="mt-1 font-semibold text-slate-100">{artifact.screenshot_count}</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Sections</p><p className="mt-1 font-semibold text-slate-100">{artifact.topic_count}</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">File size</p><p className="mt-1 font-semibold text-slate-100">{formatBytes(artifact.file_size_bytes)}</p></div>
        </div>

        <div className="mt-5 overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
          <iframe
            key={artifact.generated_at}
            title="Generated lecture PDF preview"
            src={`${pdfApi.previewUrl(video.video_id)}?v=${encodeURIComponent(artifact.generated_at)}`}
            className="h-[70vh] min-h-[520px] w-full"
          />
        </div>

        <div className="mt-5 rounded-xl border border-emerald-800/60 bg-emerald-950/30 p-4 text-sm leading-6 text-emerald-100">
          This PDF was generated only after the latest coverage audit passed. It contains every trusted screenshot exactly once; the final review can change ordering but cannot bypass the trusted-set safety gate.
        </div>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          <a href={pdfApi.downloadUrl(video.video_id)} className="rounded-xl bg-emerald-300 px-4 py-2.5 text-center font-semibold text-emerald-950 hover:bg-emerald-200">Download PDF</a>
          <button type="button" onClick={() => setStep("REVIEW")} className="rounded-xl border border-emerald-800 px-4 py-2.5 font-medium text-emerald-100 hover:border-emerald-600">Adjust PDF Settings</button>
          <button type="button" onClick={onBackToCoverage} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Back to Coverage</button>
          <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
        </div>
      </section>
    );
  }

  const busy = step === "GENERATING";
  const progress = Math.max(0, Math.min(100, job?.progress ?? 0));

  return (
    <section className="rounded-2xl border border-cyan-900/60 bg-cyan-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">Final PDF review</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      {review && (
        <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Trusted screenshots</p><p className="mt-1 font-semibold text-slate-100">{review.summary.screenshot_count}</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Lecture sections</p><p className="mt-1 font-semibold text-slate-100">{review.summary.topic_count}</p></div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Ordering</p><p className="mt-1 font-semibold text-slate-100">{orderChanged ? "Unsaved changes" : "Saved"}</p></div>
        </div>
      )}

      <div className="mt-5 rounded-xl border border-cyan-900/50 bg-cyan-950/30 p-4 text-sm leading-6 text-cyan-100">
        Use the deterministic up/down controls to reorder final pages. Every trusted screenshot must remain present exactly once. To remove or restore a screenshot, return to candidate review and then rerun the dependent transcript/topic/OCR/coverage stages.
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="space-y-3">
          {ordered.map((item, index) => (
            <article key={item.trusted_index} className="flex gap-4 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
              <img
                src={api.candidateImageUrl(video.video_id, item.candidate_index)}
                alt={`Trusted screenshot ${item.trusted_index + 1}`}
                className="h-24 w-40 shrink-0 rounded-lg border border-slate-800 object-cover"
              />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-cyan-300">Page image {index + 1}</p>
                <p className="mt-1 truncate text-sm font-semibold text-slate-100">{item.topic_title}</p>
                <p className="mt-1 text-xs text-slate-500">{formatTime(item.timestamp_seconds)} · trusted #{item.trusted_index + 1}</p>
                {(item.auto_protected || item.content_loss_risk) && <p className="mt-2 text-xs text-amber-300">Protected teaching evidence</p>}
              </div>
              <div className="flex shrink-0 flex-col gap-2">
                <button type="button" disabled={busy || index === 0} onClick={() => moveItem(index, -1)} className="rounded-lg border border-slate-700 px-2.5 py-1.5 text-xs text-slate-200 disabled:opacity-30">Up</button>
                <button type="button" disabled={busy || index === ordered.length - 1} onClick={() => moveItem(index, 1)} className="rounded-lg border border-slate-700 px-2.5 py-1.5 text-xs text-slate-200 disabled:opacity-30">Down</button>
              </div>
            </article>
          ))}
        </div>

        <aside className="h-fit rounded-xl border border-slate-800 bg-slate-950/50 p-4 lg:sticky lg:top-6">
          <p className="text-sm font-semibold text-slate-100">PDF settings</p>

          <label className="mt-4 block text-xs text-slate-400">
            Screenshot quality
            <select
              value={settings.image_quality}
              disabled={busy}
              onChange={(event) => setSettings((current) => ({ ...current, image_quality: Number(event.target.value) }))}
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
            >
              <option value={80}>Standard · smaller file</option>
              <option value={92}>High · recommended</option>
              <option value={100}>Original JPEG quality</option>
            </select>
          </label>

          <label className="mt-4 flex items-start gap-3 text-sm text-slate-300">
            <input type="checkbox" checked={settings.include_cover} disabled={busy} onChange={(event) => setSettings((current) => ({ ...current, include_cover: event.target.checked }))} className="mt-1" />
            <span>Include cover page</span>
          </label>
          <label className="mt-4 flex items-start gap-3 text-sm text-slate-300">
            <input type="checkbox" checked={settings.include_topic_dividers} disabled={busy} onChange={(event) => setSettings((current) => ({ ...current, include_topic_dividers: event.target.checked }))} className="mt-1" />
            <span>Include topic divider pages</span>
          </label>
          <label className="mt-4 flex items-start gap-3 text-sm text-slate-300">
            <input type="checkbox" checked={settings.include_context} disabled={busy} onChange={(event) => setSettings((current) => ({ ...current, include_context: event.target.checked }))} className="mt-1" />
            <span>Include OCR/speech context captions</span>
          </label>

          <button type="button" disabled={busy} onClick={resetTopicOrder} className="mt-5 w-full rounded-lg border border-cyan-800 px-3 py-2 text-sm font-medium text-cyan-100 hover:border-cyan-600 disabled:opacity-50">Reset Topic Order</button>
        </aside>
      </div>

      {busy && (
        <div className="mt-5 rounded-xl border border-emerald-900/60 bg-emerald-950/20 p-4" aria-live="polite">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-300">Generating final PDF</p>
              <p className="mt-2 text-sm text-emerald-100">{job?.message ?? "Preparing final pages..."}</p>
            </div>
            <span className="text-sm font-semibold text-emerald-200">{Math.round(progress)}%</span>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800">
            <div className="h-full rounded-full bg-emerald-300 transition-all duration-300" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      {step === "ERROR" && error && (
        <div className="mt-5 rounded-xl border border-red-900/60 bg-red-950/20 p-4 text-sm text-red-200" role="alert">
          {error}
          <button type="button" onClick={() => setStep(review ? "REVIEW" : "LOADING")} className="ml-3 underline">Return to review</button>
        </div>
      )}

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <button type="button" disabled={busy || ordered.length === 0} onClick={() => void generatePdf()} className="rounded-xl bg-cyan-300 px-4 py-2.5 font-semibold text-cyan-950 hover:bg-cyan-200 disabled:opacity-60">
          {busy ? "Generating PDF..." : "Generate Final PDF"}
        </button>
        <button type="button" disabled={busy} onClick={onBackToCoverage} className="rounded-xl border border-cyan-800 px-4 py-2.5 font-medium text-cyan-100 hover:border-cyan-600 disabled:opacity-50">Back to Coverage</button>
        <button type="button" disabled={busy} onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500 disabled:opacity-50">Choose Another Video</button>
      </div>
    </section>
  );
}
