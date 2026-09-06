from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from app.core.errors import AppError, ErrorCode

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def validate_video_id(video_id: str) -> str:
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise AppError(ErrorCode.INVALID_YOUTUBE_URL, "Please enter a valid YouTube video URL.", 400)
    return video_id


def extract_video_id(raw_url: str) -> str:
    value = raw_url.strip()
    if not value:
        raise AppError(ErrorCode.INVALID_YOUTUBE_URL, "Please enter a valid YouTube video URL.", 400)

    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise AppError(ErrorCode.INVALID_YOUTUBE_URL, "Please enter a valid YouTube video URL.", 400) from exc

    if parsed.scheme not in {"http", "https"}:
        raise AppError(ErrorCode.INVALID_YOUTUBE_URL, "Please enter a valid YouTube video URL.", 400)

    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    video_id: str | None = None

    if host == "youtu.be":
        parts = [part for part in parsed.path.split("/") if part]
        video_id = parts[0] if parts else None
    elif host in {"youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            values = parse_qs(parsed.query).get("v")
            video_id = values[0] if values else None
        else:
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] == "shorts":
                video_id = parts[1]

    if not video_id:
        raise AppError(ErrorCode.INVALID_YOUTUBE_URL, "Please enter a valid YouTube video URL.", 400)

    return validate_video_id(video_id)


def canonical_youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={validate_video_id(video_id)}"


def normalize_youtube_url(raw_url: str) -> tuple[str, str]:
    video_id = extract_video_id(raw_url)
    return video_id, canonical_youtube_url(video_id)
