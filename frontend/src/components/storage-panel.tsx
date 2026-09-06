"use client";

import type { StorageStatus } from "@/types/api";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[index]}`;
}

export function StoragePanel({ status, cleaning, onCleanup }: { status: StorageStatus | null; cleaning: boolean; onCleanup: () => void }) {
  if (!status) return null;
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/50 p-5">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <p className="text-sm font-semibold text-slate-200">Local storage</p>
          <p className="mt-1 text-xs text-slate-500">{status.prepared_video_count} prepared videos · {formatBytes(status.temp_size_bytes)} temporary data · {formatBytes(status.free_space_bytes)} free</p>
        </div>
        <button type="button" disabled={cleaning} onClick={onCleanup} className="rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-300 hover:border-slate-500 disabled:opacity-50">
          {cleaning ? "Cleaning..." : "Clean Temporary Files"}
        </button>
      </div>
    </section>
  );
}
