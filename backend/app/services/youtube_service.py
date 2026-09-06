from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import yt_dlp

from app.core.errors import AppError, ErrorCode
from app.schemas.video import VideoMetadata
from app.utils.time import format_duration
from app.utils.youtube_url import canonical_youtube_url, normalize_youtube_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class YoutubeInspection:
    video_id: str
    normalized_url: str
    raw: dict[str, Any]


class YoutubeService:
    def _extract(self, url: str) -> YoutubeInspection:
        video_id, normalized_url = normalize_youtube_url(url)
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "extract_flat": False,
        }

        logger.info("YouTube inspection started for video_id=%s", video_id)
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(normalized_url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            message = str(exc).lower()
            logger.warning("YouTube inspection failed for %s", video_id)
            if "private video" in message or "private" in message:
                raise AppError(ErrorCode.VIDEO_PRIVATE, "This YouTube video is private or cannot be accessed.", 422) from exc
            raise AppError(ErrorCode.VIDEO_UNAVAILABLE, "The YouTube video could not be accessed.", 422) from exc
        except Exception as exc:
            logger.exception("Unexpected YouTube inspection failure for %s", video_id)
            raise AppError(ErrorCode.VIDEO_UNAVAILABLE, "The YouTube video could not be accessed.", 422) from exc

        if not isinstance(info, dict):
            raise AppError(ErrorCode.VIDEO_UNAVAILABLE, "The YouTube video could not be accessed.", 422)

        actual_id = str(info.get("id") or "")
        if actual_id and actual_id != video_id:
            raise AppError(ErrorCode.VIDEO_UNAVAILABLE, "The YouTube video could not be accessed.", 422)

        return YoutubeInspection(video_id=video_id, normalized_url=normalized_url, raw=info)

    def validate(self, url: str) -> tuple[str, str]:
        inspected = self._extract(url)
        return inspected.video_id, inspected.normalized_url

    def metadata(self, url: str) -> VideoMetadata:
        inspected = self._extract(url)
        info = inspected.raw

        live_status = str(info.get("live_status") or "").lower()
        is_live = bool(info.get("is_live")) or live_status in {"is_live", "is_upcoming"}
        if is_live:
            raise AppError(ErrorCode.LIVE_VIDEO_UNSUPPORTED, "Live videos are not supported yet.", 422)

        duration_raw = info.get("duration")
        if duration_raw is None:
            raise AppError(ErrorCode.VIDEO_UNAVAILABLE, "The video duration could not be determined.", 422)
        duration_seconds = max(0, int(round(float(duration_raw))))

        title = str(info.get("title") or "Untitled YouTube video").strip()
        channel = info.get("channel") or info.get("uploader")
        thumbnail = info.get("thumbnail")

        height = info.get("height")
        resolution: str | None = None
        try:
            if height:
                resolution = f"{int(height)}p"
            else:
                requested = info.get("requested_formats") or []
                video_heights = [int(item.get("height")) for item in requested if item.get("height")]
                if video_heights:
                    resolution = f"{max(video_heights)}p"
        except (TypeError, ValueError):
            resolution = None

        logger.info("YouTube metadata ready for video_id=%s", inspected.video_id)
        return VideoMetadata(
            video_id=inspected.video_id,
            title=title,
            duration_seconds=duration_seconds,
            duration_formatted=format_duration(duration_seconds),
            channel=str(channel).strip() if channel else None,
            thumbnail_url=str(thumbnail) if thumbnail else None,
            normalized_url=canonical_youtube_url(inspected.video_id),
            is_live=False,
            resolution=resolution,
        )
