from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from app.core.errors import AppError, ErrorCode


@dataclass(frozen=True)
class SampledFrame:
    sample_index: int
    frame_index: int
    timestamp_seconds: float
    image: np.ndarray


class AdaptiveFrameStream:
    """Streams downscaled frames from FFmpeg without decoding every source frame in Python."""

    def __init__(self, ffmpeg_path: str | None = None) -> None:
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")

    @staticmethod
    def scaled_size(source_width: int, source_height: int, target_width: int) -> tuple[int, int]:
        width = max(64, min(source_width, target_width))
        height = max(2, int(round(source_height * width / max(1, source_width))))
        if height % 2:
            height += 1
        return width, height

    @staticmethod
    def _read_exact(stream, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = stream.read(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def frames(
        self,
        path: Path,
        *,
        fps: float,
        source_fps: float,
        source_width: int,
        source_height: int,
        target_width: int,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
    ) -> Iterator[SampledFrame]:
        if not self.ffmpeg_path:
            raise AppError(ErrorCode.FFMPEG_NOT_FOUND, "FFmpeg is required for adaptive visual analysis.", 503)
        if fps <= 0:
            raise ValueError("Sampling FPS must be positive.")

        width, height = self.scaled_size(source_width, source_height, target_width)
        command = [self.ffmpeg_path, "-hide_banner", "-loglevel", "error"]
        if start_seconds > 0:
            command += ["-ss", f"{start_seconds:.6f}"]
        command += ["-i", str(path)]
        if end_seconds is not None:
            duration = max(0.001, end_seconds - start_seconds)
            command += ["-t", f"{duration:.6f}"]
        command += [
            "-an",
            "-sn",
            "-dn",
            "-vf",
            f"fps={fps:.6f},scale={width}:{height}",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "pipe:1",
        ]

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdout is not None
        assert process.stderr is not None
        frame_bytes = width * height * 3
        index = 0
        try:
            while True:
                raw = self._read_exact(process.stdout, frame_bytes)
                if not raw:
                    break
                if len(raw) != frame_bytes:
                    raise AppError(ErrorCode.CHANGE_DETECTION_FAILED, "FFmpeg returned an incomplete sampled frame.", 500)
                image = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3)).copy()
                timestamp = start_seconds + (index / fps)
                source_index = max(0, int(round(timestamp * source_fps))) if source_fps > 0 else index
                yield SampledFrame(index, source_index, timestamp, image)
                index += 1
            stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
            code = process.wait()
            if code != 0:
                raise AppError(ErrorCode.CHANGE_DETECTION_FAILED, f"Adaptive FFmpeg sampling failed: {stderr or 'unknown FFmpeg error'}", 500)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
