import type { FrameTimelineSummary, VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  timeline: FrameTimelineSummary;
  analyzingChanges: boolean;
  onAnalyzeChanges: () => void;
  onChooseAnother: () => void;
}

export function FrameTimelineCard({ video, timeline, analyzingChanges, onAnalyzeChanges, onChooseAnother }: Props) {
  return (
    <section className="rounded-2xl border border-violet-900/60 bg-violet-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">✓ Video timing metadata ready</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>
      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Source frames</p><p className="mt-1 font-semibold text-slate-100">{timeline.frame_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Source FPS</p><p className="mt-1 font-semibold text-slate-100">{timeline.fps.toFixed(3)}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Resolution</p><p className="mt-1 font-semibold text-slate-100">{timeline.width}×{timeline.height}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Duration</p><p className="mt-1 font-semibold text-slate-100">{timeline.duration_seconds.toFixed(1)}s</p></div>
      </div>
      <p className="mt-5 text-sm leading-6 text-slate-300">Notify reads timing metadata without decoding every source frame. The next stage scans the full lecture at low temporal resolution, then automatically increases precision only around writing, scrolling, slide changes, and other meaningful visual activity.</p>
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <button type="button" disabled={analyzingChanges} onClick={onAnalyzeChanges} className="rounded-xl bg-violet-300 px-4 py-2.5 font-semibold text-slate-950 hover:bg-violet-200 disabled:cursor-not-allowed disabled:opacity-60">
          {analyzingChanges ? "Starting adaptive scan..." : "Run Adaptive Visual Scan"}
        </button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
