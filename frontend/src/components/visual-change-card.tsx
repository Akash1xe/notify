import type { VideoMetadata, VisualChangeSummary } from "@/types/api";

interface Props {
  video: VideoMetadata;
  changes: VisualChangeSummary;
  detectingStates: boolean;
  onDetectStates: () => void;
  onChooseAnother: () => void;
}

type AdaptiveVisualChangeSummary = VisualChangeSummary & {
  adaptive_sampling?: boolean;
  source_frame_count?: number;
  coarse_sample_count?: number;
  fine_sample_count?: number;
  analyzed_sample_count?: number;
  activity_window_count?: number;
  estimated_frame_reduction_percent?: number;
  processing_wall_seconds?: number;
};

export function VisualChangeCard({ video, changes, detectingStates, onDetectStates, onChooseAnother }: Props) {
  const adaptive = changes as AdaptiveVisualChangeSummary;
  const isAdaptive = adaptive.adaptive_sampling === true;

  return (
    <section className="rounded-2xl border border-cyan-900/60 bg-cyan-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">✓ Adaptive visual scan ready</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Source frames</p>
          <p className="mt-1 font-semibold text-slate-100">{(adaptive.source_frame_count ?? changes.compared_frame_count).toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Analyzed samples</p>
          <p className="mt-1 font-semibold text-slate-100">{(adaptive.analyzed_sample_count ?? changes.compared_frame_count).toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Activity windows</p>
          <p className="mt-1 font-semibold text-slate-100">{(adaptive.activity_window_count ?? changes.change_pair_count).toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Source frames avoided</p>
          <p className="mt-1 font-semibold text-emerald-300">{isAdaptive ? `${(adaptive.estimated_frame_reduction_percent ?? 0).toFixed(1)}%` : "—"}</p>
        </div>
      </div>

      {isAdaptive ? (
        <div className="mt-3 grid gap-3 text-sm text-slate-300 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
            <p className="text-slate-500">Coarse samples</p>
            <p className="mt-1 font-semibold text-slate-100">{(adaptive.coarse_sample_count ?? 0).toLocaleString()}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
            <p className="text-slate-500">Fine samples</p>
            <p className="mt-1 font-semibold text-slate-100">{(adaptive.fine_sample_count ?? 0).toLocaleString()}</p>
          </div>
        </div>
      ) : null}

      <div className="mt-5 rounded-xl border border-emerald-900/50 bg-emerald-950/20 p-4 text-sm text-emerald-200">
        {isAdaptive
          ? "Adaptive coverage complete: the full lecture was sampled coarsely and activity windows were rescanned at higher temporal precision."
          : changes.coverage_complete && changes.compared_every_consecutive_pair
            ? "Coverage: every consecutive frame pair verified"
            : "Coverage incomplete"}
      </div>

      <p className="mt-5 text-sm leading-6 text-slate-300">
        Static lecture time is skipped aggressively, while writing, slide changes, scrolling, and structural activity trigger a fine scan. Final screenshots are still extracted from the original prepared video at checkpoint timestamps.
      </p>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <button type="button" onClick={onDetectStates} disabled={detectingStates} className="rounded-xl bg-cyan-200 px-4 py-2.5 font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-60">
          {detectingStates ? "Starting State Detection..." : "Detect Stable Teaching States"}
        </button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
