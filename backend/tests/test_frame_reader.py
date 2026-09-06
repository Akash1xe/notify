from pathlib import Path

import cv2
import numpy as np

from app.services.frame_reader import VideoFrameReader


def make_video(path: Path, frame_count: int = 12, fps: float = 6.0) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    assert writer.isOpened()
    for index in range(frame_count):
        frame = np.full((48, 64, 3), index * 10, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_streaming_frame_reader_reports_ordered_frames(tmp_path: Path) -> None:
    path = tmp_path / "lecture.mp4"
    make_video(path)

    with VideoFrameReader(path) as reader:
        assert reader.metadata is not None
        assert reader.metadata.width == 64
        assert reader.metadata.height == 48
        packets = list(reader.frames())

    assert len(packets) == 12
    assert [packet.frame_index for packet in packets] == list(range(12))
    timestamps = [packet.timestamp_seconds for packet in packets]
    assert timestamps == sorted(timestamps)
    assert timestamps[0] == 0.0
    assert timestamps[-1] > 1.0
