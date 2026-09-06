import type { AnalysisJobResponse } from "@/types/api";

export function FrameAnalysisProgress({ job }: { job: AnalysisJobResponse }) {
  return (
    <section className="rounded-2xl border border-blue-900/60 bg-blue-950/20 p-6" aria-live="polite">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-300">Building frame timeline</p>
          <p className="mt-2 text-slate-200">{job.message}</p>
        </div>
        <span className="text-sm font-semibold text-slate-300">{Math.round(job.progress)}%</span>
      </div>
      <div className="mt-5 h-2 overflow-hidden rounded-full bg-slate-800">
        <div className="h-full rounded-full bg-blue-300 transition-all duration-300" style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }} />
      </div>
      <p className="mt-3 text-xs text-slate-500">Status: {job.status}</p>
    </section>
  );
}
