"use client";

import Image from "next/image";
import { useState } from "react";
import type { VideoMetadata } from "@/types/api";

interface Props {
  video: VideoMetadata;
  preparing: boolean;
  onPrepare: () => void;
  onChooseAnother: () => void;
}

export function VideoPreviewCard({ video, preparing, onPrepare, onChooseAnother }: Props) {
  const [imageFailed, setImageFailed] = useState(false);

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/70">
      <div className="grid gap-0 md:grid-cols-[280px_1fr]">
        <div className="relative min-h-44 bg-slate-950">
          {video.thumbnail_url && !imageFailed ? (
            <Image
              src={video.thumbnail_url}
              alt={`Thumbnail for ${video.title}`}
              fill
              sizes="(max-width: 768px) 100vw, 280px"
              className="object-cover"
              onError={() => setImageFailed(true)}
            />
          ) : (
            <div className="flex h-full min-h-44 items-center justify-center px-6 text-center text-sm text-slate-500">
              Thumbnail unavailable
            </div>
          )}
        </div>
        <div className="p-6">
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-blue-300">Video found</p>
          <h2 className="text-xl font-semibold text-white">{video.title}</h2>
          <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
            <div><dt className="text-slate-500">Channel</dt><dd className="mt-1 text-slate-200">{video.channel ?? "Unknown"}</dd></div>
            <div><dt className="text-slate-500">Duration</dt><dd className="mt-1 text-slate-200">{video.duration_formatted}</dd></div>
            <div><dt className="text-slate-500">Resolution</dt><dd className="mt-1 text-slate-200">{video.resolution ?? "Best available"}</dd></div>
            <div><dt className="text-slate-500">Source</dt><dd className="mt-1 text-slate-200">YouTube</dd></div>
          </dl>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              disabled={preparing}
              onClick={onPrepare}
              className="rounded-xl bg-blue-300 px-4 py-2.5 font-semibold text-slate-950 hover:bg-blue-200 disabled:opacity-50"
            >
              {preparing ? "Starting preparation..." : "Prepare Video"}
            </button>
            <button type="button" disabled={preparing} onClick={onChooseAnother} className="rounded-xl border border-slate-700 px-4 py-2.5 font-medium text-slate-200 hover:border-slate-500 disabled:opacity-50">
              Choose Another Video
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
