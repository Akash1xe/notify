"use client";

import { useEffect, useRef, useState } from "react";
import { TopicCard } from "@/components/topic-card";
import { ApiError, api } from "@/lib/api";
import type {
  AnalysisJobResponse,
  LectureTopicResultResponse,
  ScreenshotTranscriptAlignmentSummary,
  TranscriptSummary,
  VideoMetadata,
} from "@/types/api";

interface Props {
  video: VideoMetadata;
  transcript: TranscriptSummary;
  alignment: ScreenshotTranscriptAlignmentSummary;
  onBackToReview: () => void;
  onChooseAnother: () => void;
}

type TopicStep = "IDLE" | "RUNNING" | "READY" | "ERROR";

function formatDuration(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

function readableError(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return "Lecture topic detection failed unexpectedly.";
}

export function TranscriptCard({ video, transcript, alignment, onBackToReview, onChooseAnother }: Props) {
  const [topicStep, setTopicStep] = useState<TopicStep>("IDLE");
  const [topicJob, setTopicJob] = useState<AnalysisJobResponse | null>(null);
  const [topicResult, setTopicResult] = useState<LectureTopicResultResponse | null>(null);
  const [topicError, setTopicError] = useState<string | null>(null);
  const generation = useRef(0);

  useEffect(() => () => { generation.current += 1; }, []);

  const alignmentPercent = alignment.trusted_screenshot_count > 0
    ? Math.round((alignment.aligned_screenshot_count / alignment.trusted_screenshot_count) * 100)
    : 0;

  async function loadTopics() {
    const result = await api.getLectureTopics(video.video_id);
    setTopicResult(result);
    setTopicStep("READY");
  }

  async function pollTopicJob(jobId: string) {
    const currentGeneration = ++generation.current;
    let failures = 0;
    while (currentGeneration === generation.current) {
      try {
        const current = await api.getTopicDetectionJob(jobId);
        failures = 0;
        setTopicJob(current);
        if (current.status === "READY") {
          await loadTopics();
          return;
        }
        if (["FAILED", "INTERRUPTED", "CANCELLED"].includes(current.status)) {
          setTopicError(current.error?.message ?? current.message);
          setTopicStep("ERROR");
          return;
        }
      } catch (error) {
        failures += 1;
        if (failures >= 3) {
          setTopicError(readableError(error));
          setTopicStep("ERROR");
          return;
        }
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1250));
    }
  }

  async function startTopicDetection() {
    generation.current += 1;
    setTopicStep("RUNNING");
    setTopicJob(null);
    setTopicResult(null);
    setTopicError(null);
    try {
      const created = await api.startTopicDetection(video.video_id);
      const initial: AnalysisJobResponse = {
        job_id: created.job_id,
        video_id: created.video_id,
        job_type: "TOPIC_DETECTION",
        status: created.status,
        progress: created.status === "READY" ? 100 : 0,
        message: created.message,
        error: null,
      };
      setTopicJob(initial);
      if (created.status === "READY") {
        await loadTopics();
        return;
      }
      void pollTopicJob(created.job_id);
    } catch (error) {
      setTopicError(readableError(error));
      setTopicStep("ERROR");
    }
  }

  if (topicStep === "READY" && topicResult) {
    return (
      <TopicCard
        video={video}
        summary={topicResult.summary}
        topics={topicResult.topics}
        onBackToTranscript={() => setTopicStep("IDLE")}
        onChooseAnother={onChooseAnother}
      />
    );
  }

  const topicBusy = topicStep === "RUNNING";
  const progress = Math.max(0, Math.min(100, topicJob?.progress ?? 0));

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
        Model: <span className="font-semibold">{transcript.model_name}</span>. Each trusted screenshot is linked to speech from roughly {alignment.context_before_seconds} seconds before through {alignment.context_after_seconds} seconds after its timestamp. The raw transcript remains independently cached.
      </div>

      {alignment.unaligned_screenshot_count > 0 && (
        <div className="mt-4 rounded-xl border border-amber-900/50 bg-amber-950/20 p-4 text-sm text-amber-200">
          {alignment.unaligned_screenshot_count.toLocaleString()} trusted screenshot(s) have no nearby detected speech. They remain eligible for topic assignment; silence does not make visual content unimportant.
        </div>
      )}

      {topicBusy && (
        <div className="mt-5 rounded-xl border border-fuchsia-900/60 bg-fuchsia-950/20 p-4" aria-live="polite">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-fuchsia-300">Detecting lecture sections</p>
              <p className="mt-2 text-sm text-fuchsia-100">{topicJob?.message ?? "Starting topic detection..."}</p>
            </div>
            <span className="text-sm font-semibold text-fuchsia-200">{Math.round(progress)}%</span>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800">
            <div className="h-full rounded-full bg-fuchsia-300 transition-all duration-300" style={{ width: `${progress}%` }} />
          </div>
          <p className="mt-3 text-xs leading-5 text-slate-500">This step is deterministic and local. It uses transcript structure plus trusted screenshot timing; it does not call an external LLM.</p>
        </div>
      )}

      {topicStep === "ERROR" && topicError && (
        <div className="mt-5 rounded-xl border border-red-900/60 bg-red-950/20 p-4 text-sm text-red-200" role="alert">{topicError}</div>
      )}

      <p className="mt-5 text-sm leading-6 text-slate-400">
        Topic detection looks for coherent section boundaries rather than labeling every transcript sentence. Speech gaps, vocabulary shifts, explicit transition phrases, and strong visual transitions are combined conservatively.
      </p>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <button type="button" disabled={topicBusy} onClick={() => void startTopicDetection()} className="rounded-xl bg-fuchsia-300 px-4 py-2.5 font-semibold text-fuchsia-950 hover:bg-fuchsia-200 disabled:opacity-60">
          {topicBusy ? "Detecting Topics..." : topicStep === "ERROR" ? "Retry Topic Detection" : "Detect Lecture Topics"}
        </button>
        <button type="button" disabled={topicBusy} onClick={onBackToReview} className="rounded-xl border border-sky-800 px-4 py-2.5 font-medium text-sky-100 hover:border-sky-600 disabled:opacity-50">Back to Candidate Review</button>
        <button type="button" disabled={topicBusy} onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500 disabled:opacity-50">Choose Another Video</button>
      </div>
    </section>
  );
}
