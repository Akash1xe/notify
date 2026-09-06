import type { JobResponse } from "@/types/api";

export function PreparationProgress({ job }: { job: JobResponse }) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6" aria-live="polite">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-300">Preparing lecture</p>
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
