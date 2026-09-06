"use client";

import { useState } from "react";
import { PdfWorkflowCard } from "@/components/pdf-workflow-card";
import type { CoverageFinding, CoverageSummary } from "@/types/coverage";
import type { VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  summary: CoverageSummary;
  findings: CoverageFinding[];
  onBackToOcr: () => void;
  onChooseAnother: () => void;
}

function formatTime(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

function readable(value: string) {
  return value.toLowerCase().replaceAll("_", " ");
}

function evidencePreview(evidence: Record<string, unknown>) {
  return Object.entries(evidence)
    .slice(0, 4)
    .map(([key, value]) => `${readable(key)}: ${Array.isArray(value) ? value.join(", ") : String(value ?? "—")}`)
    .join(" · ");
}

export function CoverageCard({ video, summary, findings, onBackToOcr, onChooseAnother }: Props) {
  const [showPdf, setShowPdf] = useState(false);
  const blocking = findings.filter((finding) => finding.blocking);
  const reviews = findings.filter((finding) => !finding.blocking && finding.severity === "REVIEW");
  const warnings = findings.filter((finding) => finding.severity === "WARNING");

  if (showPdf && summary.ready_for_pdf) {
    return <PdfWorkflowCard video={video} onBackToCoverage={() => setShowPdf(false)} onChooseAnother={onChooseAnother} />;
  }

  const gateTone = blocking.length > 0 ? "text-red-300" : reviews.length > 0 ? "text-amber-300" : "text-emerald-300";
  const gateLabel = blocking.length > 0 ? "Blocked" : reviews.length > 0 ? "Ready · review notes" : "Ready";

  return (
    <section className={`rounded-2xl border p-6 ${blocking.length > 0 ? "border-red-900/60 bg-red-950/20" : "border-emerald-900/60 bg-emerald-950/20"}`}>
      <p className={`text-xs font-semibold uppercase tracking-[0.18em] ${blocking.length > 0 ? "text-red-300" : "text-emerald-300"}`}>
        {blocking.length > 0 ? "Coverage verification found confirmed blockers" : "✓ Evidence-aware coverage verification complete"}
      </p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Trusted screenshots</p><p className="mt-1 font-semibold text-slate-100">{summary.trusted_screenshot_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Windows rechecked</p><p className="mt-1 font-semibold text-slate-100">{summary.rechecked_window_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Blocking</p><p className="mt-1 font-semibold text-red-200">{summary.blocking_finding_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Review notes</p><p className="mt-1 font-semibold text-amber-200">{summary.review_finding_count ?? reviews.length}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">PDF gate</p><p className={`mt-1 font-semibold ${gateTone}`}>{gateLabel}</p></div>
      </div>

      <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-sm leading-6 text-slate-300">
        Duplicate-suppressed and explicitly dismissed stable states are now treated as represented evidence. Long speech gaps are review signals, not automatic proof that a screenshot was missed. Protected evidence and unresolved destructive transitions still block PDF generation.
      </div>

      {blocking.length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-red-300">Confirmed blocking windows</h3>
          <div className="mt-3 space-y-3">
            {blocking.slice(0, 20).map((finding) => (
              <article key={finding.finding_index} className="rounded-xl border border-red-900/50 bg-red-950/25 p-4">
                <p className="text-sm font-semibold text-red-100">{finding.reasons.map(readable).join(" + ")}</p>
                <p className="mt-1 text-xs text-slate-400">{formatTime(finding.start_seconds)} → {formatTime(finding.end_seconds)}</p>
                <p className="mt-3 text-xs leading-5 text-slate-400">{evidencePreview(finding.evidence)}</p>
              </article>
            ))}
          </div>
        </div>
      )}

      {reviews.length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-amber-300">Review notes</h3>
          <p className="mt-2 text-sm leading-6 text-amber-100">These windows are suspicious but do not prove content loss. They no longer hard-block the PDF by themselves.</p>
          <div className="mt-3 space-y-3">
            {reviews.slice(0, 12).map((finding) => (
              <article key={finding.finding_index} className="rounded-xl border border-amber-900/50 bg-amber-950/20 p-4">
                <p className="text-sm font-semibold text-amber-100">{finding.reasons.map(readable).join(" + ")}</p>
                <p className="mt-1 text-xs text-slate-400">{formatTime(finding.start_seconds)} → {formatTime(finding.end_seconds)}</p>
                <p className="mt-3 text-xs leading-5 text-slate-400">{evidencePreview(finding.evidence)}</p>
              </article>
            ))}
          </div>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="mt-6 rounded-xl border border-amber-900/50 bg-amber-950/20 p-4">
          <p className="text-sm font-semibold text-amber-200">OCR uncertainty</p>
          <p className="mt-2 text-sm leading-6 text-amber-100">{warnings.length} OCR warning(s) remain. They never delete screenshots or block the PDF because handwriting, equations, diagrams, and code can be useful even when OCR is weak.</p>
        </div>
      )}

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <button type="button" disabled={!summary.ready_for_pdf} onClick={() => setShowPdf(true)} className="rounded-xl bg-emerald-300 px-4 py-2.5 font-semibold text-emerald-950 hover:bg-emerald-200 disabled:bg-slate-700 disabled:text-slate-400 disabled:opacity-70">
          {summary.ready_for_pdf ? "Review & Generate PDF" : "Generate PDF — Confirmed Evidence Blocked"}
        </button>
        <button type="button" onClick={onBackToOcr} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Back to OCR Results</button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
