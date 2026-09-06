import type { ScreenshotCandidateSummary, VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  candidates: ScreenshotCandidateSummary;
  reviewing: boolean;
  onReview: () => void;
  onChooseAnother: () => void;
}

export function ScreenshotCandidateCard({ video, candidates, reviewing, onReview, onChooseAnother }: Props) {
  return (
    <section className="rounded-2xl border border-violet-900/60 bg-violet-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">✓ Screenshot candidates ready</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Checkpoints</p><p className="mt-1 font-semibold text-slate-100">{candidates.source_checkpoint_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Kept</p><p className="mt-1 font-semibold text-slate-100">{candidates.kept_candidate_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Duplicates</p><p className="mt-1 font-semibold text-slate-100">{candidates.duplicate_candidate_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Protected</p><p className="mt-1 font-semibold text-slate-100">{candidates.protected_kept_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Loss-risk flags</p><p className="mt-1 font-semibold text-slate-100">{candidates.content_loss_risk_count.toLocaleString()}</p></div>
      </div>

      <div className="mt-5 rounded-xl border border-emerald-900/50 bg-emerald-950/20 p-4 text-sm text-emerald-200">
        Conservative filtering remains enabled. Phase 2.5 also marks completed states that may be lost after a scene replacement or sharp visual-detail drop so review can restore them automatically.
      </div>

      <p className="mt-5 text-sm leading-6 text-slate-300">Every original checkpoint still has a manifest record, including rejected near-duplicates. Review is non-destructive and builds a separate trusted screenshot set.</p>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <button type="button" disabled={reviewing} onClick={onReview} className="rounded-xl bg-violet-300 px-4 py-2.5 font-semibold text-violet-950 hover:bg-violet-200 disabled:opacity-60">
          {reviewing ? "Preparing Review..." : "Review & Protect Candidates"}
        </button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
