import type { LectureTopic, LectureTopicSummary, VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  summary: LectureTopicSummary;
  topics: LectureTopic[];
  onBackToTranscript: () => void;
  onChooseAnother: () => void;
}

function formatTime(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

function readableReason(reason: string) {
  return reason.toLowerCase().replaceAll("_", " ");
}

export function TopicCard({ video, summary, topics, onBackToTranscript, onChooseAnother }: Props) {
  return (
    <section className="rounded-2xl border border-fuchsia-900/60 bg-fuchsia-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-fuchsia-300">✓ Lecture sections ready</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Topics</p><p className="mt-1 font-semibold text-slate-100">{summary.topic_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Transcript segments</p><p className="mt-1 font-semibold text-slate-100">{summary.transcript_segment_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Screenshots assigned</p><p className="mt-1 font-semibold text-slate-100">{summary.assigned_screenshot_count}/{summary.trusted_screenshot_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Coverage</p><p className="mt-1 font-semibold text-slate-100">{summary.coverage_complete ? "Complete" : "Incomplete"}</p></div>
      </div>

      <div className="mt-5 rounded-xl border border-fuchsia-900/50 bg-fuchsia-950/30 p-4 text-sm leading-6 text-fuchsia-100">
        Sections are detected locally from speech gaps, vocabulary shifts, transition phrases, and strong visual transitions. Topic boundaries are conservative: short sentence-level changes do not automatically become new sections.
      </div>

      <div className="mt-6 space-y-4">
        {topics.map((topic) => (
          <article key={topic.topic_index} className="rounded-xl border border-slate-800 bg-slate-950/50 p-5">
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-fuchsia-300">Section {topic.topic_index + 1}</p>
                <h3 className="mt-2 text-lg font-semibold text-slate-100">{topic.title}</h3>
                <p className="mt-1 text-sm text-slate-500">{formatTime(topic.start_seconds)} → {formatTime(topic.end_seconds)} · {formatTime(topic.duration_seconds)}</p>
              </div>
              <span className="self-start rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300">{topic.screenshot_count} screenshot{topic.screenshot_count === 1 ? "" : "s"}</span>
            </div>

            {topic.keywords.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {topic.keywords.map((keyword) => <span key={keyword} className="rounded-full bg-slate-800 px-2.5 py-1 text-xs text-slate-300">{keyword}</span>)}
              </div>
            )}

            <div className="mt-4 grid gap-3 text-xs text-slate-400 sm:grid-cols-3">
              <div><span className="text-slate-600">Speech segments</span><p className="mt-1 text-slate-300">{topic.segment_count.toLocaleString()}</p></div>
              <div><span className="text-slate-600">Words</span><p className="mt-1 text-slate-300">{topic.word_count.toLocaleString()}</p></div>
              <div><span className="text-slate-600">Boundary signal</span><p className="mt-1 text-slate-300">{topic.boundary_reasons.map(readableReason).join(" + ")}</p></div>
            </div>
          </article>
        ))}
      </div>

      <div className="mt-5 rounded-xl border border-emerald-900/50 bg-emerald-950/20 p-4 text-sm text-emerald-200">
        Every trusted screenshot is assigned to exactly one ordered section. The original transcript, screenshot manifest, and trusted screenshot set remain unchanged.
      </div>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <button type="button" disabled title="OCR and semantic enrichment come next" className="rounded-xl bg-slate-700 px-4 py-2.5 font-semibold text-slate-400 opacity-70">Enrich Screenshot Content — Next</button>
        <button type="button" onClick={onBackToTranscript} className="rounded-xl border border-fuchsia-800 px-4 py-2.5 font-medium text-fuchsia-100 hover:border-fuchsia-600">Back to Transcript</button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
