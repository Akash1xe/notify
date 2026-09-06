import type { FrameTimelineSummary, VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  timeline: FrameTimelineSummary;
  onChooseAnother: () => void;
}

export function FrameTimelineCard({ video, timeline, onChooseAnother }: Props) {
  return (
    <section className="rounded-2xl border border-violet-900/60 bg-violet-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">✓ Frame timeline ready</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>
      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Frames decoded</p><p className="mt-1 font-semibold text-slate-100">{timeline.frame_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">FPS</p><p className="mt-1 font-semibold text-slate-100">{timeline.fps.toFixed(3)}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Resolution</p><p className="mt-1 font-semibold text-slate-100">{timeline.width}×{timeline.height}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Last frame time</p><p className="mt-1 font-semibold text-slate-100">{timeline.last_timestamp_seconds.toFixed(2)}s</p></div>
      </div>
      <p className="mt-5 text-sm leading-6 text-slate-300">Every decoded frame now has an ordered timestamp on disk. Phase 2 can use this timeline for visual-change detection without loading the full lecture into memory.</p>
      <button type="button" onClick={onChooseAnother} className="mt-6 rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
    </section>
  );
}
