from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

import cv2
import numpy as np


class ChangeKind(str, Enum):
    NONE = "NONE"
    LOCAL = "LOCAL"
    STRUCTURAL = "STRUCTURAL"
    SCENE = "SCENE"


@dataclass(frozen=True)
class VisualChangeConfig:
    target_width: int = 320
    pixel_delta_threshold: int = 12
    none_mean_delta: float = 1.2
    none_changed_ratio: float = 0.002
    none_edge_ratio: float = 0.0015
    local_changed_ratio: float = 0.06
    local_bbox_area_ratio: float = 0.30
    local_mean_delta: float = 10.0
    scene_changed_ratio: float = 0.40
    scene_mean_delta: float = 32.0

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True)
class VisualSignature:
    lab_blurred: np.ndarray
    edges: np.ndarray


@dataclass(frozen=True)
class ChangeMetrics:
    kind: ChangeKind
    mean_pixel_delta: float
    changed_pixel_ratio: float
    edge_change_ratio: float
    change_bbox_area_ratio: float
    change_score: float

    def to_dict(self) -> dict[str, float | str]:
        return {
            "kind": self.kind.value,
            "mean_pixel_delta": round(self.mean_pixel_delta, 6),
            "changed_pixel_ratio": round(self.changed_pixel_ratio, 8),
            "edge_change_ratio": round(self.edge_change_ratio, 8),
            "change_bbox_area_ratio": round(self.change_bbox_area_ratio, 8),
            "change_score": round(self.change_score, 4),
        }


class VisualChangeDetector:
    """Produces compact visual signatures and compares consecutive frames.

    LOCAL changes are deliberately retained rather than discarded: a cursor, hand,
    newly written character, or annotation can all look local in a single frame
    pair. A later persistence/stability stage decides which local changes are
    transient and which represent teaching content.
    """

    def __init__(self, config: VisualChangeConfig | None = None) -> None:
        self.config = config or VisualChangeConfig()

    def signature(self, frame: np.ndarray) -> VisualSignature:
        if frame is None or frame.size == 0:
            raise ValueError("Cannot analyze an empty frame.")

        height, width = frame.shape[:2]
        target_width = min(width, max(64, self.config.target_width))
        scale = target_width / width
        target_height = max(1, int(round(height * scale)))
        if target_width != width or target_height != height:
            resized = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
        else:
            resized = frame

        lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
        lab_blurred = cv2.GaussianBlur(lab, (5, 5), 0)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray_blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray_blurred, 50, 120)
        return VisualSignature(lab_blurred=lab_blurred, edges=edges)

    def compare(self, previous: VisualSignature, current: VisualSignature) -> ChangeMetrics:
        if previous.lab_blurred.shape != current.lab_blurred.shape:
            raise ValueError("Frame signatures have different dimensions.")

        color_delta = cv2.absdiff(previous.lab_blurred, current.lab_blurred)
        # Maximum LAB-channel delta catches hue/chroma changes that a grayscale-only
        # comparator could miss while remaining inexpensive on the downscaled image.
        delta_map = np.max(color_delta, axis=2)
        mean_delta = float(np.mean(delta_map))
        changed_mask = delta_map >= self.config.pixel_delta_threshold
        changed_ratio = float(np.count_nonzero(changed_mask) / changed_mask.size)

        edge_delta = cv2.absdiff(previous.edges, current.edges)
        edge_ratio = float(np.count_nonzero(edge_delta) / edge_delta.size)

        bbox_ratio = 0.0
        ys, xs = np.nonzero(changed_mask)
        if xs.size:
            bbox_width = int(xs.max() - xs.min() + 1)
            bbox_height = int(ys.max() - ys.min() + 1)
            bbox_ratio = float((bbox_width * bbox_height) / changed_mask.size)

        config = self.config
        if (
            mean_delta <= config.none_mean_delta
            and changed_ratio <= config.none_changed_ratio
            and edge_ratio <= config.none_edge_ratio
        ):
            kind = ChangeKind.NONE
        elif changed_ratio >= config.scene_changed_ratio or mean_delta >= config.scene_mean_delta:
            kind = ChangeKind.SCENE
        elif (
            changed_ratio <= config.local_changed_ratio
            and bbox_ratio <= config.local_bbox_area_ratio
            and mean_delta <= config.local_mean_delta
        ):
            kind = ChangeKind.LOCAL
        else:
            kind = ChangeKind.STRUCTURAL

        score = 100.0 * (
            0.35 * min(1.0, mean_delta / 40.0)
            + 0.45 * min(1.0, changed_ratio / 0.35)
            + 0.20 * min(1.0, edge_ratio / 0.20)
        )

        return ChangeMetrics(
            kind=kind,
            mean_pixel_delta=mean_delta,
            changed_pixel_ratio=changed_ratio,
            edge_change_ratio=edge_ratio,
            change_bbox_area_ratio=bbox_ratio,
            change_score=score,
        )
