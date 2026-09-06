"use client";

import type { FrameTimelineSummary, VideoMetadata } from "@/types/api";

type Props = {
  video: VideoMetadata;
  timeline: FrameTimelineSummary;
  onAnalyzeChanges: () => void;
  onReset: () => void;
  disabled?: boolean;
};

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return `${minutes}m ${remaining}s`;
}

export function FrameTimelineCard({ video, timeline, onAnalyzeChanges, onReset, disabled = false }: Props) {
  return (
    <section className="panel stack-lg">
      <div>
        <p className="eyebrow">✓ Source metadata ready</p>
        <h2>{video.title}</h2>
      </div>

      <div className="metric-grid">
        <div className="metric-card"><span>Source frames</span><strong>{timeline.frame_count.toLocaleString()}</strong></div>
        <div className="metric-card"><span>FPS</span><strong>{timeline.fps.toFixed(2)}</strong></div>
        <div className="metric-card"><span>Resolution</span><strong>{timeline.width} × {timeline.height}</strong></div>
        <div className="metric-card"><span>Duration</span><strong>{formatDuration(timeline.duration_seconds)}</strong></div>
      </div>

      <div className="coverage-note coverage-note--success">
        <strong>No full-video decode at this stage</strong>
        <span>
          Notify reads source timing and stream metadata only. The next stage uses adaptive 4 FPS scanning and increases precision only
          around meaningful activity instead of comparing every original frame.
        </span>
      </div>

      <div className="actions">
        <button className="primary-button" onClick={onAnalyzeChanges} disabled={disabled}>
          {disabled ? "Starting..." : "Run Adaptive Visual Scan"}
        </button>
        <button className="secondary-button" onClick={onReset}>Choose Another Video</button>
      </div>
    </section>
  );
}
