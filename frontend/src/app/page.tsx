"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FrameAnalysisProgress } from "@/components/frame-analysis-progress";
import { FrameTimelineCard } from "@/components/frame-timeline-card";
import { PreparationProgress } from "@/components/preparation-progress";
import { ReadyCard } from "@/components/ready-card";
import { StoragePanel } from "@/components/storage-panel";
import { TeachingStateCard } from "@/components/teaching-state-card";
import { VideoPreviewCard } from "@/components/video-preview-card";
import { VisualChangeCard } from "@/components/visual-change-card";
import { YoutubeUrlForm } from "@/components/youtube-url-form";
import { ApiError, api } from "@/lib/api";
import type {
  AnalysisJobResponse,
  FrameTimelineSummary,
  JobResponse,
  StorageStatus,
  SystemStatus,
  TeachingStateSummary,
  VideoMetadata,
  VisualChangeSummary,
} from "@/types/api";

type UiStep =
  | "INPUT"
  | "LOADING_METADATA"
  | "METADATA"
  | "PREPARING"
  | "READY"
  | "ANALYZING"
  | "ANALYSIS_READY"
  | "COMPARING_CHANGES"
  | "CHANGES_READY"
  | "DETECTING_STATES"
  | "STATES_READY"
  | "ERROR";

function readableError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something unexpected happened.";
}

const isTerminalFailure = (status: string) => ["FAILED", "INTERRUPTED", "CANCELLED"].includes(status);

export default function Home() {
  const [step, setStep] = useState<UiStep>("INPUT");
  const [video, setVideo] = useState<VideoMetadata | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [analysisJob, setAnalysisJob] = useState<AnalysisJobResponse | null>(null);
  const [visualChangeJob, setVisualChangeJob] = useState<AnalysisJobResponse | null>(null);
  const [teachingStateJob, setTeachingStateJob] = useState<AnalysisJobResponse | null>(null);
  const [timeline, setTimeline] = useState<FrameTimelineSummary | null>(null);
  const [changes, setChanges] = useState<VisualChangeSummary | null>(null);
  const [states, setStates] = useState<TeachingStateSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [backendConnected, setBackendConnected] = useState<boolean | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [storage, setStorage] = useState<StorageStatus | null>(null);
  const [reusedExisting, setReusedExisting] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [startingAnalysis, setStartingAnalysis] = useState(false);
  const [startingChanges, setStartingChanges] = useState(false);
  const [startingStates, setStartingStates] = useState(false);
  const pollGeneration = useRef(0);

  const refreshStorage = useCallback(async () => {
    try { setStorage(await api.storageStatus()); } catch { /* secondary UI */ }
  }, []);

  useEffect(() => {
    void api.health().then(() => setBackendConnected(true)).catch(() => setBackendConnected(false));
    void api.systemStatus().then(setSystem).catch(() => setSystem(null));
    void refreshStorage();
  }, [refreshStorage]);

  useEffect(() => () => { pollGeneration.current += 1; }, []);

  function clearAnalysisState() {
    setAnalysisJob(null);
    setVisualChangeJob(null);
    setTeachingStateJob(null);
    setTimeline(null);
    setChanges(null);
    setStates(null);
  }

  async function loadMetadata(submittedUrl: string) {
    pollGeneration.current += 1;
    setStep("LOADING_METADATA");
    setError(null);
    setJob(null);
    clearAnalysisState();
    setReusedExisting(false);
    try {
      const response = await api.getMetadata(submittedUrl);
      setVideo(response.video);
      setStep("METADATA");
    } catch (err) {
      setError(readableError(err));
      setStep("ERROR");
    }
  }

  async function pollPreparationJob(jobId: string) {
    const generation = ++pollGeneration.current;
    let failures = 0;
    while (generation === pollGeneration.current) {
      try {
        const current = await api.getJob(jobId);
        failures = 0;
        setJob(current);
        if (current.status === "READY") {
          if (video) {
            try {
              const preparedStatus = await api.getVideoStatus(video.video_id);
              if (preparedStatus.resolution) {
                setVideo((previous) => previous ? { ...previous, resolution: preparedStatus.resolution ?? previous.resolution } : previous);
              }
            } catch { /* READY job is authoritative */ }
          }
          setStep("READY");
          await refreshStorage();
          return;
        }
        if (isTerminalFailure(current.status)) {
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

  async function prepareVideo() {
    if (!video) return;
    pollGeneration.current += 1;
    setStep("PREPARING");
    setError(null);
    clearAnalysisState();
    try {
      const created = await api.prepareVideo(video.normalized_url, video.video_id);
      setReusedExisting(created.reused_existing);
      setJob({
        job_id: created.job_id,
        video_id: created.video_id,
        status: created.status,
        progress: created.status === "READY" ? 100 : 0,
        message: created.message,
        error: null,
      });
      if (created.status === "READY") {
        setStep("READY");
        await refreshStorage();
        return;
      }
      void pollPreparationJob(created.job_id);
    } catch (err) {
      setError(readableError(err));
      setStep("ERROR");
    }
  }

  async function loadTimeline() {
    if (!video) return;
    const response = await api.getFrameTimeline(video.video_id);
    setTimeline(response.timeline);
    setStep("ANALYSIS_READY");
  }

  async function pollFrameJob(jobId: string) {
    const generation = ++pollGeneration.current;
    let failures = 0;
    while (generation === pollGeneration.current) {
      try {
        const current = await api.getAnalysisJob(jobId);
        failures = 0;
        setAnalysisJob(current);
        if (current.status === "READY") { await loadTimeline(); return; }
        if (isTerminalFailure(current.status)) {
          setError(current.error?.message ?? current.message);
          setStep("ERROR");
          return;
        }
      } catch (err) {
        failures += 1;
        if (failures >= 3) { setError(readableError(err)); setStep("ERROR"); return; }
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1250));
    }
  }

  async function startFrameAnalysis() {
    if (!video) return;
    pollGeneration.current += 1;
    setStartingAnalysis(true);
    setError(null);
    setTimeline(null);
    setChanges(null);
    setStates(null);
    try {
      const created = await api.startFrameAnalysis(video.video_id);
      const initial: AnalysisJobResponse = {
        job_id: created.job_id,
        video_id: created.video_id,
        job_type: "FRAME_TIMELINE",
        status: created.status,
        progress: created.status === "READY" ? 100 : 0,
        message: created.message,
        error: null,
      };
      setAnalysisJob(initial);
      if (created.status === "READY") { await loadTimeline(); return; }
      setStep("ANALYZING");
      void pollFrameJob(created.job_id);
    } catch (err) {
      setError(readableError(err));
      setStep("ERROR");
    } finally {
      setStartingAnalysis(false);
    }
  }

  async function loadVisualChanges() {
    if (!video) return;
    const response = await api.getVisualChanges(video.video_id);
    setChanges(response.changes);
    setStep("CHANGES_READY");
  }

  async function pollVisualChangeJob(jobId: string) {
    const generation = ++pollGeneration.current;
    let failures = 0;
    while (generation === pollGeneration.current) {
      try {
        const current = await api.getVisualChangeJob(jobId);
        failures = 0;
        setVisualChangeJob(current);
        if (current.status === "READY") { await loadVisualChanges(); return; }
        if (isTerminalFailure(current.status)) {
          setError(current.error?.message ?? current.message);
          setStep("ERROR");
          return;
        }
      } catch (err) {
        failures += 1;
        if (failures >= 3) { setError(readableError(err)); setStep("ERROR"); return; }
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1250));
    }
  }

  async function startVisualChangeAnalysis() {
    if (!video) return;
    pollGeneration.current += 1;
    setStartingChanges(true);
    setError(null);
    setChanges(null);
    setStates(null);
    try {
      const created = await api.startVisualChangeAnalysis(video.video_id);
      const initial: AnalysisJobResponse = {
        job_id: created.job_id,
        video_id: created.video_id,
        job_type: "VISUAL_CHANGE",
        status: created.status,
        progress: created.status === "READY" ? 100 : 0,
        message: created.message,
        error: null,
      };
      setVisualChangeJob(initial);
      if (created.status === "READY") { await loadVisualChanges(); return; }
      setStep("COMPARING_CHANGES");
      void pollVisualChangeJob(created.job_id);
    } catch (err) {
      setError(readableError(err));
      setStep("ERROR");
    } finally {
      setStartingChanges(false);
    }
  }

  async function loadTeachingStates() {
    if (!video) return;
    const response = await api.getTeachingStates(video.video_id);
    setStates(response.states);
    setStep("STATES_READY");
  }

  async function pollTeachingStateJob(jobId: string) {
    const generation = ++pollGeneration.current;
    let failures = 0;
    while (generation === pollGeneration.current) {
      try {
        const current = await api.getTeachingStateJob(jobId);
        failures = 0;
        setTeachingStateJob(current);
        if (current.status === "READY") { await loadTeachingStates(); return; }
        if (isTerminalFailure(current.status)) {
          setError(current.error?.message ?? current.message);
          setStep("ERROR");
          return;
        }
      } catch (err) {
        failures += 1;
        if (failures >= 3) { setError(readableError(err)); setStep("ERROR"); return; }
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1250));
    }
  }

  async function startTeachingStateAnalysis() {
    if (!video) return;
    pollGeneration.current += 1;
    setStartingStates(true);
    setError(null);
    setStates(null);
    try {
      const created = await api.startTeachingStateAnalysis(video.video_id);
      const initial: AnalysisJobResponse = {
        job_id: created.job_id,
        video_id: created.video_id,
        job_type: "TEACHING_STATE",
        status: created.status,
        progress: created.status === "READY" ? 100 : 0,
        message: created.message,
        error: null,
      };
      setTeachingStateJob(initial);
      if (created.status === "READY") { await loadTeachingStates(); return; }
      setStep("DETECTING_STATES");
      void pollTeachingStateJob(created.job_id);
    } catch (err) {
      setError(readableError(err));
      setStep("ERROR");
    } finally {
      setStartingStates(false);
    }
  }

  function reset() {
    pollGeneration.current += 1;
    setStep("INPUT");
    setVideo(null);
    setJob(null);
    clearAnalysisState();
    setError(null);
    setReusedExisting(false);
    setStartingAnalysis(false);
    setStartingChanges(false);
    setStartingStates(false);
  }

  async function cleanup() {
    setCleaning(true);
    try { await api.cleanupStorage(); await refreshStorage(); }
    catch (err) { setError(readableError(err)); }
    finally { setCleaning(false); }
  }

  async function deleteLocal() {
    if (!video) return;
    if (!window.confirm("Remove this prepared lecture and its local analysis data? The YouTube source is not affected.")) return;
    setDeleting(true);
    try { await api.deleteLocalVideo(video.video_id); await refreshStorage(); reset(); }
    catch (err) { setError(readableError(err)); }
    finally { setDeleting(false); }
  }

  const showInput = step === "INPUT" || step === "LOADING_METADATA" || (step === "ERROR" && !video);
  const teachingStateFailed = step === "ERROR" && teachingStateJob !== null;
  const visualChangeFailed = step === "ERROR" && !teachingStateFailed && visualChangeJob !== null;
  const timelineFailed = step === "ERROR" && !teachingStateFailed && !visualChangeFailed && analysisJob !== null;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-5 py-10 sm:px-8 sm:py-14">
      <header className="mb-10">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">Local lecture processor</p>
            <h1 className="mt-3 text-4xl font-bold tracking-tight text-white sm:text-5xl">Notify</h1>
          </div>
          <div className="rounded-full border border-slate-800 bg-slate-900/70 px-3 py-1.5 text-xs text-slate-400">
            Backend: {backendConnected === null ? "Checking" : backendConnected ? "Connected" : "Offline"}
          </div>
        </div>
        <p className="mt-4 max-w-2xl text-base leading-7 text-slate-400">Turn YouTube lectures into organized visual notes. The analysis now waits for stable teaching states instead of treating every pen stroke or character as a screenshot.</p>
      </header>

      {system && (!system.ffmpeg_available || !system.ffprobe_available) && (
        <div className="mb-6 rounded-xl border border-amber-900/60 bg-amber-950/20 p-4 text-sm text-amber-200">
          FFmpeg/ffprobe was not detected. Metadata lookup still works, but local video preparation requires both tools.
        </div>
      )}

      <div className="space-y-6">
        {showInput && (
          <section className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 sm:p-8">
            <h2 className="text-xl font-semibold text-white">Prepare a lecture</h2>
            <p className="mb-6 mt-2 text-sm leading-6 text-slate-400">Paste a supported YouTube lecture URL. Processing and storage stay on this computer.</p>
            <YoutubeUrlForm loading={step === "LOADING_METADATA"} onSubmit={loadMetadata} />
          </section>
        )}

        {video && step === "METADATA" && <VideoPreviewCard video={video} preparing={false} onPrepare={prepareVideo} onChooseAnother={reset} />}
        {video && step === "PREPARING" && job && <PreparationProgress job={job} />}
        {video && step === "READY" && (
          <ReadyCard video={video} reusedExisting={reusedExisting} deleting={deleting} analyzing={startingAnalysis} onStartAnalysis={startFrameAnalysis} onChooseAnother={reset} onDeleteLocal={deleteLocal} />
        )}
        {video && step === "ANALYZING" && analysisJob && <FrameAnalysisProgress job={analysisJob} />}
        {video && step === "ANALYSIS_READY" && timeline && (
          <FrameTimelineCard video={video} timeline={timeline} analyzingChanges={startingChanges} onAnalyzeChanges={startVisualChangeAnalysis} onChooseAnother={reset} />
        )}
        {video && step === "COMPARING_CHANGES" && visualChangeJob && <FrameAnalysisProgress job={visualChangeJob} />}
        {video && step === "CHANGES_READY" && changes && (
          <VisualChangeCard video={video} changes={changes} detectingStates={startingStates} onDetectStates={startTeachingStateAnalysis} onChooseAnother={reset} />
        )}
        {video && step === "DETECTING_STATES" && teachingStateJob && <FrameAnalysisProgress job={teachingStateJob} />}
        {video && step === "STATES_READY" && states && <TeachingStateCard video={video} states={states} onChooseAnother={reset} />}

        {step === "ERROR" && error && (
          <section className="rounded-2xl border border-red-900/70 bg-red-950/20 p-5" role="alert">
            <p className="font-semibold text-red-200">Could not complete that step</p>
            <p className="mt-2 text-sm text-red-300">{error}</p>
            {video && (
              <div className="mt-4 flex gap-3">
                <button
                  type="button"
                  onClick={teachingStateFailed ? startTeachingStateAnalysis : visualChangeFailed ? startVisualChangeAnalysis : timelineFailed ? startFrameAnalysis : prepareVideo}
                  className="rounded-lg bg-slate-100 px-3 py-2 text-sm font-semibold text-slate-950"
                >
                  {teachingStateFailed ? "Retry State Detection" : visualChangeFailed ? "Retry Visual Comparison" : timelineFailed ? "Retry Frame Analysis" : "Retry Preparation"}
                </button>
                <button type="button" onClick={reset} className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200">Choose Another Video</button>
              </div>
            )}
          </section>
        )}

        <StoragePanel status={storage} cleaning={cleaning} onCleanup={cleanup} />
      </div>

      <footer className="mt-auto pt-12 text-xs text-slate-600">Phase 2.3 · Continuous visual activity is grouped into stable teaching-state checkpoint candidates with pre-transition protection.</footer>
    </main>
  );
}
