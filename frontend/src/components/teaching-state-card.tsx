import type { TeachingStateSummary, VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  states: TeachingStateSummary;
  onChooseAnother: () => void;
}

export function TeachingStateCard({ video, states, onChooseAnother }: Props) {
  return (
    <section className="rounded-2xl border border-emerald-900/60 bg-emerald-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">✓ Stable teaching states ready</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Checkpoint candidates</p>
          <p className="mt-1 font-semibold text-slate-100">{states.checkpoint_count.toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Stable after change</p>
          <p className="mt-1 font-semibold text-slate-100">{states.stable_after_change_count.toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Protected before transition</p>
          <p className="mt-1 font-semibold text-slate-100">{states.pre_transition_protection_count.toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">End fallback</p>
          <p className="mt-1 font-semibold text-slate-100">{states.end_of_video_fallback_count.toLocaleString()}</p>
        </div>
      </div>

      <div className="mt-5 rounded-xl border border-emerald-900/50 bg-emerald-950/30 p-4 text-sm text-emerald-200">
        Coverage: {states.coverage_complete ? `all ${states.source_pair_count.toLocaleString()} visual transitions inspected` : "incomplete"}
      </div>

      <p className="mt-5 text-sm leading-6 text-slate-300">
        Continuous writing is now grouped temporally. The system waits for roughly {states.detector_config.stable_seconds?.toFixed(2) ?? "1.25"} seconds of visual stability before creating a normal checkpoint, so every individual letter or pen stroke does not become a screenshot.
      </p>
      <p className="mt-3 text-sm leading-6 text-slate-400">
        Short completed pauses are also protected immediately before strong slide, board, erase, or replacement transitions. These are still conservative checkpoint candidates; screenshot extraction and duplicate removal come next.
      </p>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <button type="button" disabled title="Screenshot extraction and candidate deduplication is the next milestone" className="rounded-xl bg-slate-700 px-4 py-2.5 font-semibold text-slate-400 opacity-70">
          Extract Screenshot Candidates — Next
        </button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
