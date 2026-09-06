from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

from app.core.errors import AppError, ErrorCode


@dataclass(frozen=True)
class FrameReaderMetadata:
    fps: float
    frame_count_hint: int
    width: int
    height: int


@dataclass(frozen=True)
class FramePacket:
    frame_index: int
    timestamp_seconds: float
    image: np.ndarray


class VideoFrameReader:
    """Sequential frame reader that never loads the full lecture into memory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._capture: cv2.VideoCapture | None = None
        self.metadata: FrameReaderMetadata | None = None

    def __enter__(self) -> "VideoFrameReader":
        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened():
            capture.release()
            raise AppError(ErrorCode.VIDEO_READER_FAILED, "The prepared lecture could not be opened for frame analysis.", 422)

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if width <= 0 or height <= 0:
            capture.release()
            raise AppError(ErrorCode.VIDEO_READER_FAILED, "The prepared lecture has invalid video dimensions.", 422)

        self._capture = capture
        self.metadata = FrameReaderMetadata(
            fps=max(0.0, fps),
            frame_count_hint=max(0, frame_count),
            width=width,
            height=height,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def frames(self) -> Iterator[FramePacket]:
        if self._capture is None or self.metadata is None:
            raise RuntimeError("VideoFrameReader must be used inside a context manager.")

        index = 0
        last_timestamp = 0.0
        while True:
            ok, image = self._capture.read()
            if not ok:
                break

            raw_msec = float(self._capture.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
            timestamp = raw_msec / 1000.0 if raw_msec > 0 else 0.0
            if timestamp <= 0 and self.metadata.fps > 0:
                timestamp = index / self.metadata.fps
            if timestamp < last_timestamp:
                timestamp = index / self.metadata.fps if self.metadata.fps > 0 else last_timestamp
            timestamp = max(last_timestamp, timestamp)

            yield FramePacket(frame_index=index, timestamp_seconds=timestamp, image=image)
            last_timestamp = timestamp
            index += 1
