"use client";

import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { CandidateReviewItem, TrustedScreenshotSummary, VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  summary: TrustedScreenshotSummary;
  candidates: CandidateReviewItem[];
  updatingCandidateIndex: number | null;
  onDecision: (candidateIndex: number, selected: boolean) => Promise<void>;
  onChooseAnother: () => void;
}

const PAGE_SIZE = 12;

function formatTime(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

export function CandidateReviewCard({ video, summary, candidates, updatingCandidateIndex, onDecision, onChooseAnother }: Props) {
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(candidates.length / PAGE_SIZE));
  const visible = useMemo(() => candidates.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE), [candidates, page]);

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

      <div className="mt-6 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {visible.map((candidate) => {
          const busy = updatingCandidateIndex === candidate.candidate_index;
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
                  onClick={() => void onDecision(candidate.candidate_index, !candidate.selected)}
                  className="mt-4 w-full rounded-lg border border-slate-700 px-3 py-2 text-sm font-semibold text-slate-200 hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-45"
                  title={candidate.selected && candidate.auto_protected ? "Protected because content may disappear after this frame" : undefined}
                >
                  {busy ? "Updating..." : candidate.selected ? candidate.auto_protected ? "Protected — Keep" : "Suppress" : "Restore"}
                </button>
              </div>
            </article>
          );
        })}
      </div>

      <div className="mt-6 flex items-center justify-between gap-4 text-sm text-slate-400">
        <button type="button" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))} className="rounded-lg border border-slate-700 px-3 py-2 disabled:opacity-40">Previous</button>
        <span>Page {page + 1} of {pageCount}</span>
        <button type="button" disabled={page + 1 >= pageCount} onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))} className="rounded-lg border border-slate-700 px-3 py-2 disabled:opacity-40">Next</button>
      </div>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <button type="button" disabled title="Transcript/topic enrichment comes in the next phase" className="rounded-xl bg-slate-700 px-4 py-2.5 font-semibold text-slate-400 opacity-70">Enrich With Transcript — Next</button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
