from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.errors import AppError, ErrorCode
from app.services.media_service import MediaProbe, MediaService
from app.services.storage_service import StorageService
from app.utils.youtube_url import validate_video_id


@dataclass(frozen=True)
class PreparedVideo:
    video_id: str
    title: str
    normalized_url: str
    duration_seconds: int
    local_video_path: Path
    resolution: str | None
    prepared_at: str
    status: str
    manifest: dict[str, Any]
    probe: MediaProbe


class PreparedVideoService:
    def __init__(self, storage: StorageService, media: MediaService) -> None:
        self.storage = storage
        self.media = media

    def get_prepared_video(self, video_id: str, remove_invalid: bool = True) -> PreparedVideo | None:
        validate_video_id(video_id)
        manifest = self.storage.read_video_manifest(video_id)
        path = self.storage.prepared_video_path(video_id)
        if manifest is None or not path.exists():
            return None

        expected_duration = int(manifest.get("duration_seconds") or 0)
        try:
            probe = self.media.verify(path, expected_duration=expected_duration or None)
        except AppError as exc:
            if exc.code == ErrorCode.FFMPEG_NOT_FOUND:
                raise
            if remove_invalid:
                self.storage.delete_prepared_video(video_id)
            return None
        except Exception:
            if remove_invalid:
                self.storage.delete_prepared_video(video_id)
            return None

        return PreparedVideo(
            video_id=video_id,
            title=str(manifest.get("title") or "Untitled YouTube video"),
            normalized_url=str(manifest.get("normalized_url") or ""),
            duration_seconds=expected_duration,
            local_video_path=path.resolve(),
            resolution=manifest.get("resolution"),
            prepared_at=str(manifest.get("prepared_at") or ""),
            status="READY",
            manifest=manifest,
            probe=probe,
        )
