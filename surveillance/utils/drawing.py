"""Overlay rendering: bounding boxes, zone polygons, and the HUD status bar."""

from __future__ import annotations

import time

import cv2
import numpy as np

from surveillance.types import Detection
from surveillance.zones import Zone

# BGR palette, stable per class via hashing so the same class always draws the same color.
_PALETTE = [
    (66, 135, 245), (52, 199, 89), (255, 149, 0), (255, 45, 85),
    (175, 82, 222), (90, 200, 250), (255, 214, 10), (0, 199, 190),
]


def color_for_class(class_name: str) -> tuple[int, int, int]:
    return _PALETTE[hash(class_name) % len(_PALETTE)]


def _safe_text(text: str) -> str:
    """OpenCV's Hershey fonts only cover ASCII — anything else (em dashes,
    emoji, accented characters a user might type into Settings) renders as
    garbled '?' glyphs. Replace non-ASCII characters before drawing."""
    return text.encode("ascii", "replace").decode("ascii")


def draw_zones(frame: np.ndarray, zones: list[Zone], armed: bool) -> np.ndarray:
    overlay = frame.copy()
    h, w = frame.shape[:2]
    for zone in zones:
        pts = np.array(zone.to_pixels(w, h), dtype=np.int32)
        if len(pts) < 3:
            continue
        color = zone.color if zone.kind == "restricted" and armed else (150, 150, 150)
        cv2.fillPoly(overlay, [pts], color)
    frame = cv2.addWeighted(overlay, 0.18, frame, 0.82, 0)
    for zone in zones:
        pts = np.array(zone.to_pixels(w, h), dtype=np.int32)
        if len(pts) < 3:
            continue
        color = zone.color if zone.kind == "restricted" and armed else (150, 150, 150)
        cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
        label = f"{zone.name} ({'ARMED' if zone.kind == 'restricted' and armed else zone.kind})"
        anchor = tuple(pts[0])
        cv2.putText(frame, _safe_text(label), (anchor[0] + 4, anchor[1] - 6), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, color, 2, cv2.LINE_AA)
    return frame


def draw_detections(frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
    for det in detections:
        x1, y1, x2, y2 = (int(v) for v in det.bbox)
        color = color_for_class(det.class_name)
        thickness = 3 if det.zone else 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
        label = _safe_text(f"{det.class_name} {det.confidence:.0%}")
        if det.track_id is not None:
            label += f" #{det.track_id}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, max(0, y1 - th - 8)), (x1 + tw + 6, y1), color, -1)
        cv2.putText(frame, label, (x1 + 3, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


def draw_hud(frame: np.ndarray, *, site_name: str, camera_id: str, armed: bool,
             backend_label: str, object_count: int, fps: float) -> np.ndarray:
    h, w = frame.shape[:2]
    bar_h = 34
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_h), (20, 20, 20), -1)
    cv2.rectangle(overlay, (0, h - bar_h), (w, h), (20, 20, 20), -1)
    frame = cv2.addWeighted(overlay, 0.55, frame, 0.45, 0)

    status_color = (60, 60, 255) if armed else (140, 140, 140)
    status_text = "ARMED" if armed else "DISARMED"
    cv2.circle(frame, (16, bar_h // 2), 6, status_color, -1)
    header = _safe_text(f"{status_text}  {site_name} / {camera_id}")
    cv2.putText(frame, header, (30, bar_h // 2 + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(frame, timestamp, (w - 175, bar_h // 2 + 5), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (255, 255, 255), 1, cv2.LINE_AA)

    footer = _safe_text(f"{backend_label}  |  objects: {object_count}  |  {fps:.1f} FPS")
    cv2.putText(frame, footer, (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return frame
