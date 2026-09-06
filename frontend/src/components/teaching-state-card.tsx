"use client";

import { useEffect, useRef, useState } from "react";
import { ScreenshotCandidateCard } from "@/components/screenshot-candidate-card";
import { ApiError, api } from "@/lib/api";
import type { AnalysisJobResponse, ScreenshotCandidateSummary, TeachingStateSummary, VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  states: TeachingStateSummary;
  onChooseAnother: () => void;
}

type CandidateStep = "IDLE" | "EXTRACTING" | "READY" | "ERROR";

function readableError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Screenshot candidate extraction failed unexpectedly.";
}

export function TeachingStateCard({ video, states, onChooseAnother }: Props) {
  const [step, setStep] = useState<CandidateStep>("IDLE");
  const [job, setJob] = useState<AnalysisJobResponse | null>(null);
  const [candidates, setCandidates] = useState<ScreenshotCandidateSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);

  useEffect(() => () => { generation.current += 1; }, []);

  async function loadCandidates() {
    const response = await api.getScreenshotCandidates(video.video_id);
    setCandidates(response.candidates);
    setStep("READY");
  }

  async function pollCandidateJob(jobId: string) {
    const currentGeneration = ++generation.current;
    let failures = 0;
    while (currentGeneration === generation.current) {
      try {
        const current = await api.getScreenshotCandidateJob(jobId);
        failures = 0;
        setJob(current);
        if (current.status === "READY") {
          await loadCandidates();
          return;
        }
        if (["FAILED", "INTERRUPTED", "CANCELLED"].includes(current.status)) {
          setError(current.error?.message ?? current.message);
          setStep("ERROR");
          return;
        }
      } catch (err) {
        failures += 1;
        if (failures >= 3) {
          setError(readableError(err));
          setStep("ERROR");
          return;
        }
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1250));
    }
  }

  async function startExtraction() {
    generation.current += 1;
    setStep("EXTRACTING");
    setError(null);
    setCandidates(null);
    setJob(null);
    try {
      const created = await api.startScreenshotCandidateAnalysis(video.video_id);
      const initial: AnalysisJobResponse = {
        job_id: created.job_id,
        video_id: created.video_id,
        job_type: "SCREENSHOT_CANDIDATE",
        status: created.status,
        progress: created.status === "READY" ? 100 : 0,
        message: created.message,
        error: null,
      };
      setJob(initial);
      if (created.status === "READY") {
        await loadCandidates();
        return;
      }
      void pollCandidateJob(created.job_id);
    } catch (err) {
      setError(readableError(err));
      setStep("ERROR");
    }
  }

  if (step === "READY" && candidates) {
    return <ScreenshotCandidateCard video={video} candidates={candidates} onChooseAnother={onChooseAnother} />;
  }

  if (step === "EXTRACTING") {
    const progress = Math.max(0, Math.min(100, job?.progress ?? 0));
    return (
      <section className="rounded-2xl border border-violet-900/60 bg-violet-950/20 p-6" aria-live="polite">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-300">Extracting screenshot candidates</p>
            <p className="mt-2 text-slate-200">{job?.message ?? "Starting screenshot extraction..."}</p>
          </div>
          <span className="text-sm font-semibold text-slate-300">{Math.round(progress)}%</span>
        </div>
        <div className="mt-5 h-2 overflow-hidden rounded-full bg-slate-800">
          <div className="h-full rounded-full bg-violet-300 transition-all duration-300" style={{ width: `${progress}%` }} />
        </div>
        <p className="mt-3 text-xs text-slate-500">The prepared video is decoded sequentially; only teaching-state checkpoint frames are saved.</p>
      </section>
    );
  }

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
        Continuous writing is grouped temporally. The system waits for roughly {states.detector_config.stable_seconds?.toFixed(2) ?? "1.25"} seconds of visual stability before creating a normal checkpoint, so individual letters and pen strokes do not each become screenshots.
      </p>
      <p className="mt-3 text-sm leading-6 text-slate-400">
        The next action extracts the actual checkpoint images and applies intentionally conservative near-duplicate filtering. Protected transition and final-content checkpoints are always retained.
      </p>

      {step === "ERROR" && error && (
        <div className="mt-5 rounded-xl border border-red-900/60 bg-red-950/20 p-4 text-sm text-red-200" role="alert">
          {error}
        </div>
      )}

      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <button type="button" onClick={startExtraction} className="rounded-xl bg-violet-200 px-4 py-2.5 font-semibold text-violet-950 hover:bg-violet-100">
          {step === "ERROR" ? "Retry Screenshot Extraction" : "Extract Screenshot Candidates"}
        </button>
        <button type="button" onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500">Choose Another Video</button>
      </div>
    </section>
  );
}
