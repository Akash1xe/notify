"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { TranscriptCard } from "@/components/transcript-card";
import { ApiError, api } from "@/lib/api";
import type {
  AnalysisJobResponse,
  CandidateReviewItem,
  TranscriptResultResponse,
  TrustedScreenshotSummary,
  VideoMetadata,
} from "@/types/api";

interface Props {
  video: VideoMetadata;
  summary: TrustedScreenshotSummary;
  candidates: CandidateReviewItem[];
  updatingCandidateIndex: number | null;
  onDecision: (candidateIndex: number, selected: boolean) => Promise<void>;
  onChooseAnother: () => void;
}

const PAGE_SIZE = 12;
type TranscriptStep = "IDLE" | "RUNNING" | "READY" | "ERROR";

function formatTime(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

function readableError(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return "Transcript generation failed unexpectedly.";
}

export function CandidateReviewCard({ video, summary, candidates, updatingCandidateIndex, onDecision, onChooseAnother }: Props) {
  const [page, setPage] = useState(0);
  const [transcriptStep, setTranscriptStep] = useState<TranscriptStep>("IDLE");
  const [transcriptionJob, setTranscriptionJob] = useState<AnalysisJobResponse | null>(null);
  const [transcriptResult, setTranscriptResult] = useState<TranscriptResultResponse | null>(null);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);
  const transcriptGeneration = useRef(0);
  const pageCount = Math.max(1, Math.ceil(candidates.length / PAGE_SIZE));
  const visible = useMemo(() => candidates.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE), [candidates, page]);

  useEffect(() => () => { transcriptGeneration.current += 1; }, []);

  async function loadTranscriptResult() {
    const result = await api.getTranscriptResult(video.video_id);
    setTranscriptResult(result);
    setTranscriptStep("READY");
  }

  async function pollTranscription(jobId: string) {
    const generation = ++transcriptGeneration.current;
    let failures = 0;
    while (generation === transcriptGeneration.current) {
      try {
        const current = await api.getTranscriptionJob(jobId);
        failures = 0;
        setTranscriptionJob(current);
        if (current.status === "READY") {
          await loadTranscriptResult();
          return;
        }
        if (["FAILED", "INTERRUPTED", "CANCELLED"].includes(current.status)) {
          setTranscriptError(current.error?.message ?? current.message);
          setTranscriptStep("ERROR");
          return;
        }
      } catch (error) {
        failures += 1;
        if (failures >= 3) {
          setTranscriptError(readableError(error));
          setTranscriptStep("ERROR");
          return;
        }
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1250));
    }
  }

  async function startTranscription() {
    transcriptGeneration.current += 1;
    setTranscriptStep("RUNNING");
    setTranscriptError(null);
    setTranscriptResult(null);
    setTranscriptionJob(null);
    try {
      const created = await api.startTranscription(video.video_id);
      const initial: AnalysisJobResponse = {
        job_id: created.job_id,
        video_id: created.video_id,
        job_type: "TRANSCRIPTION",
        status: created.status,
        progress: created.status === "READY" ? 100 : 0,
        message: created.message,
        error: null,
      };
      setTranscriptionJob(initial);
      if (created.status === "READY") {
        await loadTranscriptResult();
        return;
      }
      void pollTranscription(created.job_id);
    } catch (error) {
      setTranscriptError(readableError(error));
      setTranscriptStep("ERROR");
    }
  }

  async function updateReviewDecision(candidateIndex: number, selected: boolean) {
    transcriptGeneration.current += 1;
    setTranscriptStep("IDLE");
    setTranscriptResult(null);
    setTranscriptionJob(null);
    setTranscriptError(null);
    await onDecision(candidateIndex, selected);
  }

  if (transcriptStep === "READY" && transcriptResult) {
    return (
      <TranscriptCard
        video={video}
        transcript={transcriptResult.transcript}
        alignment={transcriptResult.alignment}
        onBackToReview={() => setTranscriptStep("IDLE")}
        onChooseAnother={onChooseAnother}
      />
    );
  }

  const transcriptBusy = transcriptStep === "RUNNING";
  const progress = Math.max(0, Math.min(100, transcriptionJob?.progress ?? 0));

  return (
    <section className="rounded-2xl border border-cyan-900/60 bg-cyan-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">✓ Candidate review ready</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Trusted screenshots</p><p className="mt-1 font-semibold text-slate-100">{summary.selected_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Auto-protected</p><p className="mt-1 font-semibold text-slate-100">{summary.auto_protected_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Restored duplicates</p><p className="mt-1 font-semibold text-slate-100">{summary.restored_suppressed_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Manual suppressions</p><p className="mt-1 font-semibold text-slate-100">{summary.manual_suppress_count.toLocaleString()}</p></div>
      </div>

      <div className="mt-5 rounded-xl border border-cyan-900/50 bg-cyan-950/30 p-4 text-sm text-cyan-100">
        Protected candidates cannot be suppressed accidentally. Near-duplicates remain restorable, and every decision rebuilds a separate ordered trusted set without deleting the original candidate manifest.
      </div>

      {transcriptBusy && (
        <div className="mt-5 rounded-xl border border-sky-900/60 bg-sky-950/30 p-4" aria-live="polite">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-300">Local transcript enrichment</p>
              <p className="mt-2 text-sm text-sky-100">{transcriptionJob?.message ?? "Starting transcript generation..."}</p>
            </div>
            <span className="text-sm font-semibold text-sky-200">{Math.round(progress)}%</span>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800">
            <div className="h-full rounded-full bg-sky-300 transition-all duration-300" style={{ width: `${progress}%` }} />
          </div>
          <p className="mt-3 text-xs leading-5 text-slate-500">The first run can take longer because faster-whisper may download the configured model locally. No custom model training is required.</p>
        </div>
      )}

      {transcriptStep === "ERROR" && transcriptError && (
        <div className="mt-5 rounded-xl border border-red-900/60 bg-red-950/20 p-4 text-sm text-red-200" role="alert">{transcriptError}</div>
      )}

      <div className="mt-6 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {visible.map((candidate) => {
          const busy = transcriptBusy || updatingCandidateIndex === candidate.candidate_index;
          return (
            <article key={candidate.candidate_index} className={`overflow-hidden rounded-xl border ${candidate.selected ? "border-emerald-800/70" : "border-slate-800"} bg-slate-950/50`}>
              <img
                src={api.candidateImageUrl(video.video_id, candidate.candidate_index)}
                alt={`Lecture candidate at ${formatTime(candidate.timestamp_seconds)}`}
                className="aspect-video w-full bg-slate-900 object-contain"
                loading="lazy"
              />
              <div className="p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium text-slate-100">#{candidate.candidate_index + 1} · {formatTime(candidate.timestamp_seconds)}</p>
                  <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${candidate.selected ? "bg-emerald-950 text-emerald-300" : "bg-slate-800 text-slate-400"}`}>
                    {candidate.selected ? "IN TRUSTED SET" : "SUPPRESSED"}
                  </span>
                </div>
                <p className="mt-2 text-xs text-slate-500">{candidate.reason.replaceAll("_", " ")}</p>

                <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
                  {candidate.protected && <span className="rounded bg-amber-950/60 px-2 py-1 text-amber-300">transition protected</span>}
                  {candidate.content_loss_risk && <span className="rounded bg-red-950/60 px-2 py-1 text-red-300">content-loss risk</span>}
                  {!candidate.kept && <span className="rounded bg-violet-950/60 px-2 py-1 text-violet-300">dedup suppressed</span>}
                  {candidate.manual_decision !== null && <span className="rounded bg-blue-950/60 px-2 py-1 text-blue-300">manual decision</span>}
                </div>

                <button
                  type="button"
                  disabled={busy || (candidate.selected && candidate.auto_protected)}
                  onClick={() => void updateReviewDecision(candidate.candidate_index, !candidate.selected)}
                  className="mt-4 w-full rounded-lg border border-slate-700 px-3 py-2 text-sm font-semibold text-slate-200 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-45"
                  title={candidate.selected && candidate.auto_protected ? "Protected because content may disappear after this frame" : undefined}
                >
                  {busy && updatingCandidateIndex === candidate.candidate_index ? "Updating..." : candidate.selected ? candidate.auto_protected ? "Protected — Keep" : "Suppress" : "Restore"}
                </button>
              </div>
            </article>
          );
        })}
      </div>

      <div className="mt-6 flex items-center justify-between gap-4 text-sm text-slate-400">
        <button type="button" disabled={page === 0 || transcriptBusy} onClick={() => setPage((value) => Math.max(0, value - 1))} className="rounded-lg border border-slate-700 px-3 py-2 disabled:opacity-40">Previous</button>
        <span>Page {page + 1} of {pageCount}</span>
        <button type="button" disabled={page + 1 >= pageCount || transcriptBusy} onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))} className="rounded-lg border border-slate-700 px-3 py-2 disabled:opacity-40">Next</button>
      </div>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <button type="button" disabled={transcriptBusy} onClick={() => void startTranscription()} className="rounded-xl bg-sky-300 px-4 py-2.5 font-semibold text-sky-950 hover:bg-sky-200 disabled:opacity-60">
          {transcriptBusy ? "Generating Transcript..." : transcriptStep === "ERROR" ? "Retry Transcript Enrichment" : "Enrich With Transcript"}
        </button>
        <button type="button" disabled={transcriptBusy} onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500 disabled:opacity-50">Choose Another Video</button>
      </div>
    </section>
  );
}
