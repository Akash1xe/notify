import type { OcrSummary, ScreenshotContentSummary, TopicContentSummary, VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  ocr: OcrSummary;
  content: ScreenshotContentSummary;
  topics: TopicContentSummary[];
  onBackToTopics: () => void;
  onChooseAnother: () => void;
}

export function OcrCard({ video, ocr, content, topics, onBackToTopics, onChooseAnother }: Props) {
  const textPercent = ocr.trusted_screenshot_count > 0
    ? Math.round((ocr.text_detected_count / ocr.trusted_screenshot_count) * 100)
    : 0;

  return (
    <section className="rounded-2xl border border-amber-900/60 bg-amber-950/20 p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-300">✓ Screenshot content enriched</p>
      <h2 className="mt-3 text-xl font-semibold text-white">{video.title}</h2>

      <div className="mt-5 grid gap-3 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Screenshots scanned</p><p className="mt-1 font-semibold text-slate-100">{ocr.processed_screenshot_count}/{ocr.trusted_screenshot_count}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Visible text found</p><p className="mt-1 font-semibold text-slate-100">{ocr.text_detected_count} · {textPercent}%</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">OCR words</p><p className="mt-1 font-semibold text-slate-100">{ocr.total_word_count.toLocaleString()}</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Avg confidence</p><p className="mt-1 font-semibold text-slate-100">{ocr.average_confidence.toFixed(1)}%</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"><p className="text-slate-500">Coverage</p><p className="mt-1 font-semibold text-slate-100">{content.coverage_complete ? "Complete" : "Incomplete"}</p></div>
      </div>

      <div className="mt-5 rounded-xl border border-amber-900/50 bg-amber-950/30 p-4 text-sm leading-6 text-amber-100">
        OCR engine: <span className="font-semibold">{ocr.engine}</span> · language {ocr.language} · PSM {ocr.psm}. Raw OCR is cached separately from topic enrichment, so topic regrouping can reuse the unchanged screenshot text.
      </div>

      {(ocr.no_text_count > 0 || ocr.low_confidence_count > 0) && (
        <div className="mt-4 rounded-xl border border-cyan-900/50 bg-cyan-950/20 p-4 text-sm leading-6 text-cyan-100">
          {ocr.no_text_count > 0 && <p>{ocr.no_text_count.toLocaleString()} screenshot(s) produced no OCR text.</p>}
          {ocr.low_confidence_count > 0 && <p>{ocr.low_confidence_count.toLocaleString()} screenshot(s) produced low-confidence OCR text.</p>}
          <p className="mt-2 text-cyan-200">These screenshots stay in the trusted set. Handwriting, equations, diagrams, and code can remain important even when OCR is empty or uncertain.</p>
        </div>
      )}

      <div className="mt-6 space-y-4">
        {topics.map((topic) => (
          <article key={topic.topic_index} className="rounded-xl border border-slate-800 bg-slate-950/50 p-5">
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-300">Section {topic.topic_index + 1}</p>
                <h3 className="mt-2 text-lg font-semibold text-slate-100">{topic.title}</h3>
              </div>
              <span className="self-start rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300">
                {topic.screenshots_with_ocr_text}/{topic.screenshot_count} with OCR text
              </span>
            </div>

            <div className="mt-4 grid gap-3 text-xs text-slate-400 sm:grid-cols-2">
              <div><span className="text-slate-600">Visible OCR words</span><p className="mt-1 text-slate-300">{topic.ocr_word_count.toLocaleString()}</p></div>
              <div><span className="text-slate-600">Trusted screenshots</span><p className="mt-1 text-slate-300">{topic.screenshot_count.toLocaleString()}</p></div>
            </div>

            {topic.visual_keywords.length > 0 ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {topic.visual_keywords.map((keyword) => <span key={keyword} className="rounded-full bg-amber-950/60 px-2.5 py-1 text-xs text-amber-200">{keyword}</span>)}
              </div>
            ) : (
              <p className="mt-4 text-xs text-slate-500">No reliable visual keywords were extracted for this section. Its screenshots remain preserved.</p>
            )}
          </article>
        ))}
      </div>

      <div className="mt-5 rounded-xl border border-emerald-900/50 bg-emerald-950/20 p-4 text-sm leading-6 text-emerald-200">
        Every trusted screenshot now has an OCR record plus an enriched record containing its visible text, nearby teacher speech, and lecture-topic context. Original image/transcript/topic evidence remains unchanged.
      </div>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <button type="button" disabled title="Coverage verification is the next milestone" className="rounded-xl bg-slate-700 px-4 py-2.5 font-semibold text-slate-400 opacity-70">Verify Lecture Coverage — Next</button>
        <button type="button" onClick={onBackToTopics} className="rounded-xl border border-amber-800 px-4 py-2.5 font-medium text-amber-100 hover:border-amber-600">Back to Topics</button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
