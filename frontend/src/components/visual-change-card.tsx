"use client";

import type { VisualChangeSummary, VideoMetadata } from "@/types/api";

type Props = {
  video: VideoMetadata;
  changes: VisualChangeSummary;
  onDetectStates: () => void;
  onReset: () => void;
  disabled?: boolean;
};

export function VisualChangeCard({ video, changes, onDetectStates, onReset, disabled = false }: Props) {
  return (
    <section className="panel stack-lg">
      <div>
        <p className="eyebrow">✓ Adaptive visual scan ready</p>
        <h2>{video.title}</h2>
      </div>

      <div className="metric-grid">
        <div className="metric-card">
          <span>Analyzed samples</span>
          <strong>{changes.compared_frame_count.toLocaleString()}</strong>
        </div>
        <div className="metric-card">
          <span>Sampled transitions</span>
          <strong>{changes.compared_pair_count.toLocaleString()}</strong>
        </div>
        <div className="metric-card">
          <span>Structural changes</span>
          <strong>{changes.structural_change_count.toLocaleString()}</strong>
        </div>
        <div className="metric-card">
          <span>Scene changes</span>
          <strong>{changes.scene_change_count.toLocaleString()}</strong>
        </div>
      </div>

      <div className="coverage-note coverage-note--success">
        <strong>Adaptive coverage ready</strong>
        <span>
          The scanner now samples the full lecture at low temporal resolution and automatically increases precision around writing,
          scrolling, structural changes, and scene transitions. Final screenshots still come from the original prepared video.
        </span>
      </div>

      <p className="muted">
        Local changes remain conservative because handwriting and code edits can be small. Activity windows are rescanned at higher
        temporal resolution before stable teaching states are selected.
      </p>

      <div className="actions">
        <button className="primary-button" onClick={onDetectStates} disabled={disabled}>
          {disabled ? "Starting..." : "Detect Stable Teaching States"}
        </button>
        <button className="secondary-button" onClick={onReset}>Choose Another Video</button>
      </div>
    </section>
  );
}
