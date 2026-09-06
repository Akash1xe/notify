import type { VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  reusedExisting: boolean;
  deleting: boolean;
  analyzing: boolean;
  onStartAnalysis: () => void;
  onChooseAnother: () => void;
  onDeleteLocal: () => void;
}

export function ReadyCard({ video, reusedExisting, deleting, analyzing, onStartAnalysis, onChooseAnother, onDeleteLocal }: Props) {
  return (
    <section className="rounded-2xl border border-emerald-900/70 bg-emerald-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">✓ Lecture ready</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>
      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-300">
        <span>Duration: {video.duration_formatted}</span>
        <span>Local quality: {video.resolution ?? "prepared"}</span>
      </div>
      {reusedExisting && <p className="mt-4 text-sm text-emerald-200">Existing prepared video found and verified; no re-download was needed.</p>}
      <p className="mt-4 text-sm text-slate-300">Video is ready for sequential frame timeline analysis.</p>
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <button type="button" disabled={analyzing} onClick={onStartAnalysis} className="rounded-xl bg-blue-200 px-4 py-2.5 font-semibold text-slate-950 hover:bg-blue-100 disabled:opacity-60">
          {analyzing ? "Starting Analysis..." : "Start Frame Analysis"}
        </button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
        <button type="button" disabled={deleting || analyzing} onClick={onDeleteLocal} className="rounded-xl border border-red-900/70 px-4 py-2.5 font-medium text-red-300 hover:border-red-700 disabled:opacity-50">
          {deleting ? "Removing..." : "Remove local copy"}
        </button>
      </div>
    </section>
  );
}
