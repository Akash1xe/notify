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
  const warnings = findings.filter((finding) => !finding.blocking);

  if (showPdf && summary.ready_for_pdf) {
    return (
      <PdfWorkflowCard
        video={video}
        onBackToCoverage={() => setShowPdf(false)}
        onChooseAnother={onChooseAnother}
      />
    );
  }

  return (
    <section className={`rounded-2xl border p-6 ${summary.coverage_passed ? "border-emerald-900/60 bg-emerald-950/20" : "border-red-900/60 bg-red-950/20"}`}>
      <p className={`text-xs font-semibold uppercase tracking-[0.18em] ${summary.coverage_passed ? "text-emerald-300" : "text-red-300"}`}>
        {summary.coverage_passed ? "✓ Coverage verification passed" : "Coverage verification requires review"}
      </p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Trusted screenshots</p><p className="mt-1 font-semibold text-slate-100">{summary.trusted_screenshot_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Windows rechecked</p><p className="mt-1 font-semibold text-slate-100">{summary.rechecked_window_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Blocking findings</p><p className="mt-1 font-semibold text-slate-100">{summary.blocking_finding_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Warnings</p><p className="mt-1 font-semibold text-slate-100">{summary.warning_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">PDF gate</p><p className={`mt-1 font-semibold ${summary.ready_for_pdf ? "text-emerald-300" : "text-red-300"}`}>{summary.ready_for_pdf ? "Ready" : "Blocked"}</p></div>
      </div>

      <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-sm leading-6 text-slate-300">
        The audit cross-checks strong frame changes, stable-state checkpoints, protected candidates, trusted screenshots, transcript density, lecture topics, and OCR uncertainty. It fails closed: unresolved important windows block PDF generation instead of being silently ignored.
      </div>

      {blocking.length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-red-300">Blocking windows</h3>
          <div className="mt-3 space-y-3">
            {blocking.slice(0, 20).map((finding) => (
              <article key={finding.finding_index} className="rounded-xl border border-red-900/50 bg-red-950/25 p-4">
                <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start">
                  <div>
                    <p className="text-sm font-semibold text-red-100">{finding.reasons.map(readable).join(" + ")}</p>
                    <p className="mt-1 text-xs text-slate-400">{formatTime(finding.start_seconds)} → {formatTime(finding.end_seconds)}</p>
                  </div>
                  <span className="self-start rounded-full border border-red-800 px-2.5 py-1 text-xs font-semibold text-red-200">{finding.severity}</span>
                </div>
                <p className="mt-3 text-xs leading-5 text-slate-400">{evidencePreview(finding.evidence)}</p>
                <p className="mt-2 text-xs text-red-300">Rechecked against the available evidence layers; this finding remains unresolved.</p>
              </article>
            ))}
          </div>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="mt-6 rounded-xl border border-amber-900/50 bg-amber-950/20 p-4">
          <p className="text-sm font-semibold text-amber-200">Non-blocking uncertainty</p>
          <p className="mt-2 text-sm leading-6 text-amber-100">{warnings.length} OCR uncertainty warning(s) remain. They do not remove screenshots or block the PDF gate because handwriting, equations, diagrams, and code may be important even without reliable OCR text.</p>
        </div>
      )}

      {summary.coverage_passed && (
        <div className="mt-5 rounded-xl border border-emerald-800/60 bg-emerald-950/30 p-4 text-sm leading-6 text-emerald-100">
          No blocking missed-content signal remains after the audit. The final PDF stage preserves every trusted screenshot and allows page reordering without weakening the coverage decision.
        </div>
      )}

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <button
          type="button"
          disabled={!summary.ready_for_pdf}
          title={summary.ready_for_pdf ? "Open final PDF review" : "Resolve blocking coverage findings before PDF generation"}
          onClick={() => setShowPdf(true)}
          className="rounded-xl bg-emerald-300 px-4 py-2.5 font-semibold text-emerald-950 hover:bg-emerald-200 disabled:bg-slate-700 disabled:text-slate-400 disabled:opacity-70"
        >
          {summary.ready_for_pdf ? "Review & Generate PDF" : "Generate PDF — Coverage Blocked"}
        </button>
        <button type="button" onClick={onBackToOcr} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Back to OCR Results</button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
