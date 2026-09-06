import type { VideoMetadata, VisualChangeSummary } from "@/types/api";

interface Props {
  video: VideoMetadata;
  changes: VisualChangeSummary;
  detectingStates: boolean;
  onDetectStates: () => void;
  onChooseAnother: () => void;
}

export function VisualChangeCard({ video, changes, detectingStates, onDetectStates, onChooseAnother }: Props) {
  return (
    <section className="rounded-2xl border border-cyan-900/60 bg-cyan-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">✓ Visual change map ready</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Consecutive pairs</p>
          <p className="mt-1 font-semibold text-slate-100">{changes.compared_pair_count.toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Local changes</p>
          <p className="mt-1 font-semibold text-slate-100">{changes.local_change_count.toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Structural changes</p>
          <p className="mt-1 font-semibold text-slate-100">{changes.structural_change_count.toLocaleString()}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <p className="text-slate-500">Scene changes</p>
          <p className="mt-1 font-semibold text-slate-100">{changes.scene_change_count.toLocaleString()}</p>
        </div>
      </div>

      <div className="mt-5 rounded-xl border border-emerald-900/50 bg-emerald-950/20 p-4 text-sm text-emerald-200">
        Coverage: {changes.coverage_complete && changes.compared_every_consecutive_pair ? "every consecutive frame pair verified" : "incomplete"}
      </div>

      <p className="mt-5 text-sm leading-6 text-slate-300">
        Local changes remain preserved because a cursor, hand movement, and newly written character can look similar in a single frame pair. The next temporal pass decides when the screen has actually reached a stable teaching state.
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
