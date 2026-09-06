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
  return Object.entries(evidence).slice(0, 4)
    .map(([key, value]) => `${readable(key)}: ${Array.isArray(value) ? value.join(", ") : String(value ?? "—")}`)
    .join(" · ");
}

function FindingList({ title, findings, tone }: { title: string; findings: CoverageFinding[]; tone: "red" | "amber" }) {
  if (findings.length === 0) return null;
  const red = tone === "red";
  return (
    <div className="mt-6">
      <h3 className={`text-sm font-semibold uppercase tracking-[0.14em] ${red ? "text-red-300" : "text-amber-300"}`}>{title}</h3>
      <div className="mt-3 space-y-3">
        {findings.slice(0, 20).map((finding) => (
          <article key={finding.finding_index} className={`rounded-xl border p-4 ${red ? "border-red-900/50 bg-red-950/25" : "border-amber-900/50 bg-amber-950/20"}`}>
            <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start">
              <div>
                <p className={`text-sm font-semibold ${red ? "text-red-100" : "text-amber-100"}`}>{finding.reasons.map(readable).join(" + ")}</p>
                <p className="mt-1 text-xs text-slate-400">{formatTime(finding.start_seconds)} → {formatTime(finding.end_seconds)}</p>
              </div>
              <span className={`self-start rounded-full border px-2.5 py-1 text-xs font-semibold ${red ? "border-red-800 text-red-200" : "border-amber-800 text-amber-200"}`}>
                {finding.disposition}
              </span>
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-400">{evidencePreview(finding.evidence)}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

export function CoverageCard({ video, summary, findings, onBackToOcr, onChooseAnother }: Props) {
  const [showPdf, setShowPdf] = useState(false);
  const hardBlocks = findings.filter((finding) => finding.disposition === "BLOCK");
  const reviews = findings.filter((finding) => finding.disposition === "REVIEW");
  const warnings = findings.filter((finding) => finding.disposition === "WARNING");

  if (showPdf && summary.ready_for_pdf) {
    return <PdfWorkflowCard video={video} onBackToCoverage={() => setShowPdf(false)} onChooseAnother={onChooseAnother} />;
  }

  const gateReady = summary.pdf_gate_status === "READY";
  const gateReview = summary.pdf_gate_status === "REVIEW_REQUIRED";
  return (
    <section className={`rounded-2xl border p-6 ${gateReady ? "border-emerald-900/60 bg-emerald-950/20" : gateReview ? "border-amber-900/60 bg-amber-950/20" : "border-red-900/60 bg-red-950/20"}`}>
      <p className={`text-xs font-semibold uppercase tracking-[0.18em] ${gateReady ? "text-emerald-300" : gateReview ? "text-amber-300" : "text-red-300"}`}>
        {gateReady ? "✓ Coverage verification passed" : gateReview ? "Coverage review required" : "Coverage verification blocked"}
      </p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Trusted screenshots</p><p className="mt-1 font-semibold text-slate-100">{summary.trusted_screenshot_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Hard blockers</p><p className="mt-1 font-semibold text-slate-100">{summary.hard_blocking_finding_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Needs review</p><p className="mt-1 font-semibold text-slate-100">{summary.review_required_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Warnings</p><p className="mt-1 font-semibold text-slate-100">{summary.warning_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">PDF gate</p><p className={`mt-1 font-semibold ${gateReady ? "text-emerald-300" : gateReview ? "text-amber-300" : "text-red-300"}`}>{summary.pdf_gate_status.replaceAll("_", " ")}</p></div>
      </div>

      <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-sm leading-6 text-slate-300">
        Long speech gaps no longer block the PDF by themselves. Notify first checks whether a stable state is already represented by a trusted screenshot or a conservatively matched duplicate. Only genuinely unrepresented visual evidence is escalated for review; protected or lost-content evidence remains a hard blocker.
      </div>

      <FindingList title="Hard blockers" findings={hardBlocks} tone="red" />
      <FindingList title="Visual states that need review" findings={reviews} tone="amber" />

      {warnings.length > 0 && (
        <div className="mt-6 rounded-xl border border-cyan-900/50 bg-cyan-950/20 p-4">
          <p className="text-sm font-semibold text-cyan-200">Non-blocking uncertainty</p>
          <p className="mt-2 text-sm leading-6 text-cyan-100">{warnings.length} warning(s) remain. OCR uncertainty and strong motion without unique stable teaching content do not remove screenshots or block the PDF.</p>
        </div>
      )}

      {gateReview && (
        <div className="mt-5 rounded-xl border border-amber-900/50 bg-amber-950/20 p-4 text-sm leading-6 text-amber-100">
          These are not confirmed misses. They are stable states that are not represented in the current trusted set. Review the screenshot candidates, keep any unique teaching state that matters, then rerun the dependent stages and coverage.
        </div>
      )}

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <button type="button" disabled={!summary.ready_for_pdf} onClick={() => setShowPdf(true)}
          className="rounded-xl bg-emerald-300 px-4 py-2.5 font-semibold text-emerald-950 hover:bg-emerald-200 disabled:bg-slate-700 disabled:text-slate-400 disabled:opacity-70">
          {summary.ready_for_pdf ? "Review & Generate PDF" : gateReview ? "Generate PDF — Review Required" : "Generate PDF — Coverage Blocked"}
        </button>
        <button type="button" onClick={onBackToOcr} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Back to OCR Results</button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
