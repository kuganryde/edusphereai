"""Shared lightweight data types used across the detection/tracking/video layers.

Kept dependency-free (no cv2/ultralytics imports) to avoid circular imports
between ``video.stream`` (which can emit simulated detections in demo mode)
and ``detection.detector`` / ``detection.tracker``.
"""

from __future__ import annotations

import dataclasses

BBox = tuple[float, float, float, float]  # x1, y1, x2, y2 in pixel coordinates


@dataclasses.dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: BBox
    track_id: int | None = None
    zone: str | None = None  # populated once matched against a zone, if any
