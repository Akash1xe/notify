import type { ScreenshotCandidateSummary, VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  candidates: ScreenshotCandidateSummary;
  onChooseAnother: () => void;
}

export function ScreenshotCandidateCard({ video, candidates, onChooseAnother }: Props) {
  return (
    <section className="rounded-2xl border border-violet-900/60 bg-violet-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">✓ Screenshot candidates ready</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Checkpoints considered</p>
          <p className="mt-1 font-semibold text-slate-100">{candidates.source_checkpoint_count.toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Screenshots kept</p>
          <p className="mt-1 font-semibold text-slate-100">{candidates.kept_candidate_count.toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Near-duplicates removed</p>
          <p className="mt-1 font-semibold text-slate-100">{candidates.duplicate_candidate_count.toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Protected screenshots kept</p>
          <p className="mt-1 font-semibold text-slate-100">{candidates.protected_kept_count.toLocaleString()}</p>
        </div>
      </div>

      <div className="mt-5 rounded-xl border border-emerald-900/50 bg-emerald-950/20 p-4 text-sm text-emerald-200">
        Conservative filtering: {candidates.deduplication_conservative ? "enabled" : "disabled"}. Protected pre-transition and end-of-video states are never automatically discarded as duplicates.
      </div>

      <p className="mt-5 text-sm leading-6 text-slate-300">
        The retained images are now real JPEG screenshot candidates extracted from the prepared lecture. Duplicate decisions require both a close perceptual hash and a very small pixel-distance score, reducing the risk of deleting a frame that contains newly written teaching content.
      </p>
      <p className="mt-3 text-sm leading-6 text-slate-400">
        Every original checkpoint still has a manifest record, including rejected near-duplicates, so a later review or coverage stage can restore a suppressed frame if needed.
      </p>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <button type="button" disabled title="Candidate review and stronger content protection is the next milestone" className="rounded-xl bg-slate-700 px-4 py-2.5 font-semibold text-slate-400 opacity-70">
          Review & Protect Candidates — Next
        </button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
