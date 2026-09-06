"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { PreparationProgress } from "@/components/preparation-progress";
import { ReadyCard } from "@/components/ready-card";
import { StoragePanel } from "@/components/storage-panel";
import { VideoPreviewCard } from "@/components/video-preview-card";
import { YoutubeUrlForm } from "@/components/youtube-url-form";
import { ApiError, api } from "@/lib/api";
import type { JobResponse, StorageStatus, SystemStatus, VideoMetadata } from "@/types/api";

type UiStep = "INPUT" | "LOADING_METADATA" | "METADATA" | "PREPARING" | "READY" | "ERROR";

function readableError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something unexpected happened.";
}

export default function Home() {
  const [step, setStep] = useState<UiStep>("INPUT");
  const [url, setUrl] = useState("");
  const [video, setVideo] = useState<VideoMetadata | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [backendConnected, setBackendConnected] = useState<boolean | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [storage, setStorage] = useState<StorageStatus | null>(null);
  const [reusedExisting, setReusedExisting] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const pollGeneration = useRef(0);

  const refreshStorage = useCallback(async () => {
    try { setStorage(await api.storageStatus()); } catch { /* storage is secondary UI */ }
  }, []);

  useEffect(() => {
    void api.health().then(() => setBackendConnected(true)).catch(() => setBackendConnected(false));
    void api.systemStatus().then(setSystem).catch(() => setSystem(null));
    void refreshStorage();
  }, [refreshStorage]);

  useEffect(() => () => { pollGeneration.current += 1; }, []);

  async function loadMetadata(submittedUrl: string) {
    pollGeneration.current += 1;
    setStep("LOADING_METADATA");
    setError(null);
    setUrl(submittedUrl);
    setJob(null);
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

  async function pollJob(jobId: string) {
    const generation = ++pollGeneration.current;
    let transientFailures = 0;
    while (generation === pollGeneration.current) {
      try {
        const current = await api.getJob(jobId);
        transientFailures = 0;
        setJob(current);
        if (current.status === "READY") {
          if (video) {
            try {
              const preparedStatus = await api.getVideoStatus(video.video_id);
              if (preparedStatus.resolution) {
                setVideo((previous) => previous ? { ...previous, resolution: preparedStatus.resolution ?? previous.resolution } : previous);
              }
            } catch { /* READY job remains authoritative for the current session */ }
          }
          setStep("READY");
          await refreshStorage();
          return;
        }
        if (["FAILED", "INTERRUPTED", "CANCELLED"].includes(current.status)) {
          setError(current.error?.message ?? current.message);
          setStep("ERROR");
          return;
        }
      } catch (err) {
        transientFailures += 1;
        if (transientFailures >= 3) {
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
    setStep("PREPARING");
    setError(null);
    try {
      const created = await api.prepareVideo(video.normalized_url, video.video_id);
      setReusedExisting(created.reused_existing);
      const initialJob: JobResponse = {
        job_id: created.job_id,
        video_id: created.video_id,
        status: created.status,
        progress: created.status === "READY" ? 100 : 0,
        message: created.message,
        error: null,
      };
      setJob(initialJob);
      if (created.status === "READY") {
        try {
          const preparedStatus = await api.getVideoStatus(video.video_id);
          if (preparedStatus.resolution) {
            setVideo((previous) => previous ? { ...previous, resolution: preparedStatus.resolution ?? previous.resolution } : previous);
          }
        } catch { /* Existing READY media has already been verified by the prepare endpoint. */ }
        setStep("READY");
        await refreshStorage();
        return;
      }
      void pollJob(created.job_id);
    } catch (err) {
      setError(readableError(err));
      setStep("ERROR");
    }
  }

  function reset() {
    pollGeneration.current += 1;
    setStep("INPUT");
    setUrl("");
    setVideo(null);
    setJob(null);
    setError(null);
    setReusedExisting(false);
  }

  async function cleanup() {
    setCleaning(true);
    try {
      await api.cleanupStorage();
      await refreshStorage();
    } catch (err) {
      setError(readableError(err));
    } finally {
      setCleaning(false);
    }
  }

  async function deleteLocal() {
    if (!video) return;
    const confirmed = window.confirm("Remove this prepared lecture from local storage? The YouTube source is not affected.");
    if (!confirmed) return;
    setDeleting(true);
    try {
      await api.deleteLocalVideo(video.video_id);
      await refreshStorage();
      reset();
    } catch (err) {
      setError(readableError(err));
    } finally {
      setDeleting(false);
    }
  }

  const showInput = step === "INPUT" || step === "LOADING_METADATA" || (step === "ERROR" && !video);

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
        <p className="mt-4 max-w-2xl text-base leading-7 text-slate-400">Turn YouTube lectures into organized visual notes. Phase 1 prepares a verified local video for the frame engine.</p>
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

        {video && step === "METADATA" && (
          <VideoPreviewCard video={video} preparing={false} onPrepare={prepareVideo} onChooseAnother={reset} />
        )}

        {video && step === "PREPARING" && job && <PreparationProgress job={job} />}

        {video && step === "READY" && (
          <ReadyCard video={video} reusedExisting={reusedExisting} deleting={deleting} onChooseAnother={reset} onDeleteLocal={deleteLocal} />
        )}

        {step === "ERROR" && error && (
          <section className="rounded-2xl border border-red-900/70 bg-red-950/20 p-5" role="alert">
            <p className="font-semibold text-red-200">Could not complete that step</p>
            <p className="mt-2 text-sm text-red-300">{error}</p>
            {video && (
              <div className="mt-4 flex gap-3">
                <button type="button" onClick={prepareVideo} className="rounded-lg bg-slate-100 px-3 py-2 text-sm font-semibold text-slate-950">Retry Preparation</button>
                <button type="button" onClick={reset} className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200">Choose Another Video</button>
              </div>
            )}
          </section>
        )}

        <StoragePanel status={storage} cleaning={cleaning} onCleanup={cleanup} />
      </div>

      <footer className="mt-auto pt-12 text-xs text-slate-600">Phase 1 · Video acquisition and local preparation only. Frame analysis starts in Phase 2.</footer>
    </main>
  );
}
