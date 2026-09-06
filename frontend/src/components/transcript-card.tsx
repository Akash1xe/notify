import type { ScreenshotTranscriptAlignmentSummary, TranscriptSummary, VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  transcript: TranscriptSummary;
  alignment: ScreenshotTranscriptAlignmentSummary;
  onBackToReview: () => void;
  onChooseAnother: () => void;
}

function formatDuration(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

export function TranscriptCard({ video, transcript, alignment, onBackToReview, onChooseAnother }: Props) {
  const alignmentPercent = alignment.trusted_screenshot_count > 0
    ? Math.round((alignment.aligned_screenshot_count / alignment.trusted_screenshot_count) * 100)
    : 0;

  return (
    <section className="rounded-2xl border border-sky-900/60 bg-sky-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">✓ Timestamped transcript ready</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Segments</p><p className="mt-1 font-semibold text-slate-100">{transcript.segment_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Words</p><p className="mt-1 font-semibold text-slate-100">{transcript.word_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Duration</p><p className="mt-1 font-semibold text-slate-100">{formatDuration(transcript.duration_seconds)}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Language</p><p className="mt-1 font-semibold text-slate-100">{transcript.detected_language.toUpperCase()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Screenshots aligned</p><p className="mt-1 font-semibold text-slate-100">{alignment.aligned_screenshot_count}/{alignment.trusted_screenshot_count} · {alignmentPercent}%</p></div>
      </div>

      <div className="mt-5 rounded-xl border border-sky-900/50 bg-sky-950/30 p-4 text-sm leading-6 text-sky-100">
        Model: <span className="font-semibold">{transcript.model_name}</span>. Each trusted screenshot is now linked to speech from roughly {alignment.context_before_seconds} seconds before through {alignment.context_after_seconds} seconds after its timestamp. The raw timestamped transcript is cached independently, so changing screenshot review decisions only requires realignment.
      </div>

      {alignment.unaligned_screenshot_count > 0 && (
        <div className="mt-4 rounded-xl border border-amber-900/50 bg-amber-950/20 p-4 text-sm text-amber-200">
          {alignment.unaligned_screenshot_count.toLocaleString()} trusted screenshot(s) have no nearby detected speech. They remain in the trusted set; silence does not mean the visual content is unimportant.
        </div>
      )}

      <p className="mt-5 text-sm leading-6 text-slate-400">
        The next milestone will group these timestamped speech segments and trusted screenshots into lecture topics/sections. No semantic topic labels are being invented in this step.
      </p>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <button type="button" disabled title="Semantic topic detection is the next milestone" className="rounded-xl bg-slate-700 px-4 py-2.5 font-semibold text-slate-400 opacity-70">Detect Lecture Topics — Next</button>
        <button type="button" onClick={onBackToReview} className="rounded-xl border border-sky-800 px-4 py-2.5 font-medium text-sky-100 hover:border-sky-600">Back to Candidate Review</button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
