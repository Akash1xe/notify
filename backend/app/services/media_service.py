from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MediaProbe:
    duration_seconds: float
    width: int
    height: int
    has_video: bool
    has_audio: bool


class MediaService:
    @property
    def ffmpeg_path(self) -> str | None:
        return shutil.which("ffmpeg")

    @property
    def ffprobe_path(self) -> str | None:
        return shutil.which("ffprobe")

    def require_tools(self) -> None:
        if not self.ffmpeg_path or not self.ffprobe_path:
            raise AppError(
                ErrorCode.FFMPEG_NOT_FOUND,
                "FFmpeg and ffprobe are required to prepare videos. Install FFmpeg and try again.",
                503,
            )

    def probe(self, path: Path) -> MediaProbe:
        self.require_tools()
        if not path.exists() or path.stat().st_size <= 0:
            raise AppError(ErrorCode.MEDIA_VERIFICATION_FAILED, "The prepared video file could not be verified.", 422)

        command = [
            self.ffprobe_path or "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height",
            "-of", "json",
            str(path),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
            payload = json.loads(result.stdout or "{}")
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
            logger.warning("ffprobe verification failed for %s", path)
            raise AppError(ErrorCode.MEDIA_VERIFICATION_FAILED, "The prepared video file could not be verified.", 422) from exc

        streams = payload.get("streams") or []
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if not video_streams:
            raise AppError(ErrorCode.MEDIA_VERIFICATION_FAILED, "The prepared file does not contain a readable video stream.", 422)

        format_data = payload.get("format") or {}
        try:
            duration = float(format_data.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        if duration <= 0:
            raise AppError(ErrorCode.MEDIA_VERIFICATION_FAILED, "The prepared video duration is invalid.", 422)

        first_video = video_streams[0]
        width = int(first_video.get("width") or 0)
        height = int(first_video.get("height") or 0)
        if width <= 0 or height <= 0:
            raise AppError(ErrorCode.MEDIA_VERIFICATION_FAILED, "The prepared video dimensions are invalid.", 422)

        return MediaProbe(
            duration_seconds=duration,
            width=width,
            height=height,
            has_video=True,
            has_audio=bool(audio_streams),
        )

    def verify(self, path: Path, expected_duration: int | None = None) -> MediaProbe:
        probe = self.probe(path)
        if expected_duration and expected_duration > 0:
            tolerance = max(3.0, expected_duration * 0.01)
            if abs(probe.duration_seconds - expected_duration) > tolerance:
                raise AppError(
                    ErrorCode.MEDIA_VERIFICATION_FAILED,
                    "The downloaded lecture appears incomplete and could not be verified.",
                    422,
                )
        return probe

    def normalize_to_mp4(self, source: Path, destination: Path) -> None:
        self.require_tools()
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy_command = [
            self.ffmpeg_path or "ffmpeg", "-y", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-movflags", "+faststart", str(destination),
        ]
        try:
            subprocess.run(copy_command, capture_output=True, text=True, check=True, timeout=None)
            return
        except (subprocess.SubprocessError, OSError):
            logger.info("Stream-copy remux failed for %s; using compatibility transcode", source)

        transcode_command = [
            self.ffmpeg_path or "ffmpeg", "-y", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(destination),
        ]
        try:
            subprocess.run(transcode_command, capture_output=True, text=True, check=True, timeout=None)
        except (subprocess.SubprocessError, OSError) as exc:
            raise AppError(ErrorCode.MEDIA_MERGE_FAILED, "FFmpeg could not prepare the video.", 500) from exc
