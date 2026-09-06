from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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

    @classmethod
    def from_environment(cls) -> "Settings":
        project_root = Path(__file__).resolve().parents[3]
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
        )


settings = Settings.from_environment()
