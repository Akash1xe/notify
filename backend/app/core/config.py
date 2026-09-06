from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


@dataclass(frozen=True)
class Settings:
    project_root: Path
    downloads_dir: Path
    temp_dir: Path
    output_dir: Path
    frontend_origin: str
    max_video_height: int
    temp_retention_hours: int
    min_free_space_bytes: int
    whisper_model: str
    whisper_language: str
    whisper_device: str
    whisper_compute_type: str
    tesseract_cmd: str | None
    ocr_language: str
    ocr_psm: int
    analysis_coarse_fps: float
    analysis_fine_fps: float
    analysis_coarse_width: int
    analysis_fine_width: int
    analysis_stable_seconds: float
    analysis_pre_window_padding_seconds: float
    analysis_post_window_padding_seconds: float
    analysis_window_merge_gap_seconds: float

    @classmethod
    def from_environment(cls) -> "Settings":
        project_root = Path(__file__).resolve().parents[3]
        tesseract_cmd = os.getenv("TESSERACT_CMD")
        return cls(
            project_root=project_root,
            downloads_dir=project_root / "downloads",
            temp_dir=project_root / "temp",
            output_dir=project_root / "output",
            frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
            max_video_height=int(os.getenv("MAX_VIDEO_HEIGHT", "720")),
            temp_retention_hours=int(os.getenv("TEMP_RETENTION_HOURS", "24")),
            min_free_space_bytes=int(os.getenv("MIN_FREE_SPACE_BYTES", str(512 * 1024 * 1024))),
            whisper_model=os.getenv("WHISPER_MODEL", "small.en"),
            whisper_language=os.getenv("WHISPER_LANGUAGE", "en"),
            whisper_device=os.getenv("WHISPER_DEVICE", "cpu"),
            whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
            tesseract_cmd=tesseract_cmd.strip() if tesseract_cmd and tesseract_cmd.strip() else None,
            ocr_language=os.getenv("OCR_LANGUAGE", "eng"),
            ocr_psm=int(os.getenv("OCR_PSM", "11")),
            analysis_coarse_fps=_float_env("ANALYSIS_COARSE_FPS", 4.0, 1.0, 8.0),
            analysis_fine_fps=_float_env("ANALYSIS_FINE_FPS", 12.0, 4.0, 24.0),
            analysis_coarse_width=_int_env("ANALYSIS_COARSE_WIDTH", 320, 128, 640),
            analysis_fine_width=_int_env("ANALYSIS_FINE_WIDTH", 640, 256, 960),
            analysis_stable_seconds=_float_env("ANALYSIS_STABLE_SECONDS", 1.25, 0.5, 3.0),
            analysis_pre_window_padding_seconds=_float_env("ANALYSIS_PRE_WINDOW_PADDING_SECONDS", 1.0, 0.0, 5.0),
            analysis_post_window_padding_seconds=_float_env("ANALYSIS_POST_WINDOW_PADDING_SECONDS", 2.0, 0.0, 8.0),
            analysis_window_merge_gap_seconds=_float_env("ANALYSIS_WINDOW_MERGE_GAP_SECONDS", 2.0, 0.0, 10.0),
        )


settings = Settings.from_environment()
