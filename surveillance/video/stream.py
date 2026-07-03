"""Frame sources: webcam, RTSP/IP camera, uploaded video file, and a fully
synthetic demo feed that requires no camera hardware at all.

Every source implements the same tiny interface (:class:`FrameSource`) so the
rest of the application never needs to know where the pixels came from.
"""

from __future__ import annotations

import math
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path

import cv2
import numpy as np

from surveillance.types import Detection

FRAME_WIDTH = 960
FRAME_HEIGHT = 540


class FrameSource(ABC):
    """Common interface for anything that can hand us BGR ``np.ndarray`` frames."""

    label: str = "Unknown source"

    @abstractmethod
    def read(self) -> np.ndarray | None:
        """Return the next BGR frame, or ``None`` if unavailable this tick."""

    def release(self) -> None:  # pragma: no cover - default no-op
        pass

    @property
    def is_connected(self) -> bool:
        return True

    def simulated_detections(self) -> list[Detection] | None:
        """Return None for real sources. Demo source overrides this to supply
        ground-truth detections instead of running the AI model on cartoon
        shapes it drew itself."""
        return None


class _OpenCVSource(FrameSource):
    """Shared plumbing for any source backed by ``cv2.VideoCapture``."""

    def __init__(
        self,
        cap_target,
        label: str,
        loop: bool = False,
        api_preference: int = cv2.CAP_ANY,
        timeout_ms: int | None = None,
    ) -> None:
        self.label = label
        self._loop = loop
        if timeout_ms is not None:
            # Bounds how long a bad/unreachable camera can freeze the UI —
            # without this, a dead RTSP URL can block cv2.VideoCapture()
            # for 30s+ on its own internal default.
            params = [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms,
            ]
            self._cap = cv2.VideoCapture(cap_target, api_preference, params)
        else:
            self._cap = cv2.VideoCapture(cap_target, api_preference)
        if self._cap.isOpened():
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    @property
    def is_connected(self) -> bool:
        return bool(self._cap is not None and self._cap.isOpened())

    def read(self) -> np.ndarray | None:
        if not self.is_connected:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            if self._loop:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self._cap.read()
                if not ok:
                    return None
            else:
                return None
        return cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()


class WebcamSource(_OpenCVSource):
    """Local camera attached to the machine running the app (e.g. a guard
    house workstation with a USB/UVC camera)."""

    def __init__(self, device_index: int = 0) -> None:
        super().__init__(device_index, label=f"Local Webcam #{device_index}", loop=False,
                          timeout_ms=5000)


class RTSPSource(_OpenCVSource):
    """Networked IP camera (RTSP/HTTP MJPEG/etc.) — the typical real-world
    CCTV integration path."""

    def __init__(self, url: str) -> None:
        # RTSP defaults to UDP transport, which silently drops packets on any
        # network hiccup (Wi-Fi interference, bandwidth contention) — this is
        # what produces FFmpeg's "reference picture missing during reorder" /
        # "mmco: unref short failure" / macroblock decode errors once a frame
        # arrives corrupted or out of order. Forcing TCP makes the OS
        # retransmit lost packets instead, trading a little latency for a
        # much cleaner stream. `setdefault` so an operator who has
        # deliberately set this env var (e.g. to force UDP for lower latency
        # on a rock-solid wired link) isn't overridden.
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        super().__init__(url, label=f"IP Camera ({url})", loop=False,
                          api_preference=cv2.CAP_FFMPEG, timeout_ms=5000)


class FileSource(_OpenCVSource):
    """A previously recorded / uploaded video file, looped for continuous
    review or testing."""

    def __init__(self, path: str | Path) -> None:
        super().__init__(str(path), label=f"Video File ({Path(path).name})", loop=True)


class DemoSource(FrameSource):
    """A fully synthetic guard-house gate scene, generated frame-by-frame with
    OpenCV drawing primitives. Requires no camera, no network, and no model
    download — used for demos, UI testing, and CI smoke tests.

    Because the "person" and "car" are drawn shapes rather than real-world
    objects, a real object-detection model will *not* reliably recognize
    them. Instead, this source reports its own ground-truth bounding boxes
    via :meth:`simulated_detections`, clearly labeled in the UI as simulated
    so the demo never claims AI results it didn't actually produce.
    """

    label = "Demo Scene (Simulated)"

    def __init__(self) -> None:
        self._start = time.time()
        self._last_detections: list[Detection] = []
        self._cycle_seconds = 22.0

    @property
    def is_connected(self) -> bool:
        return True

    def read(self) -> np.ndarray | None:
        t = time.time() - self._start
        frame = self._render_background()
        detections: list[Detection] = []

        cycle_t = t % self._cycle_seconds
        person_bbox = self._person_position(cycle_t)
        if person_bbox is not None:
            self._draw_person(frame, person_bbox)
            detections.append(Detection("person", 0.93, person_bbox))

        car_bbox = self._car_position(t % 9.0)
        if car_bbox is not None:
            self._draw_car(frame, car_bbox)
            detections.append(Detection("car", 0.88, car_bbox))

        self._draw_hud(frame, t)
        self._last_detections = detections
        return frame

    def simulated_detections(self) -> list[Detection] | None:
        return list(self._last_detections)

    # -- scene rendering -------------------------------------------------

    def _render_background(self) -> np.ndarray:
        frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        # Sky gradient
        for y in range(0, int(FRAME_HEIGHT * 0.55)):
            shade = int(40 + (y / (FRAME_HEIGHT * 0.55)) * 40)
            frame[y, :] = (shade + 20, shade + 10, shade)
        # Ground
        ground_top = int(FRAME_HEIGHT * 0.55)
        frame[ground_top:, :] = (48, 58, 55)
        # Road / walkway
        cv2.rectangle(frame, (0, int(FRAME_HEIGHT * 0.62)), (FRAME_WIDTH, int(FRAME_HEIGHT * 0.78)),
                       (60, 60, 60), -1)
        # Gate posts + booth (the "guard house")
        cv2.rectangle(frame, (int(FRAME_WIDTH * 0.50), int(FRAME_HEIGHT * 0.35)),
                       (int(FRAME_WIDTH * 0.64), int(FRAME_HEIGHT * 0.72)), (90, 90, 100), -1)
        cv2.rectangle(frame, (int(FRAME_WIDTH * 0.52), int(FRAME_HEIGHT * 0.40)),
                       (int(FRAME_WIDTH * 0.62), int(FRAME_HEIGHT * 0.52)), (150, 190, 210), -1)
        cv2.putText(frame, "GUARD HOUSE", (int(FRAME_WIDTH * 0.505), int(FRAME_HEIGHT * 0.34)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
        for post_x in (0.30, 0.95):
            cv2.rectangle(frame, (int(FRAME_WIDTH * post_x), int(FRAME_HEIGHT * 0.40)),
                           (int(FRAME_WIDTH * post_x) + 8, int(FRAME_HEIGHT * 0.75)), (70, 70, 80), -1)
        return frame

    def _person_position(self, cycle_t: float) -> tuple[float, float, float, float] | None:
        # Phase 1 (0-6s): approach from the left
        # Phase 2 (6-16s): loiter near the gate (inside the restricted zone)
        # Phase 3 (16-22s): walk off to the right
        if cycle_t < 6.0:
            progress = cycle_t / 6.0
            cx = 0.05 + progress * (0.56 - 0.05)
        elif cycle_t < 16.0:
            cx = 0.56 + 0.01 * math.sin(cycle_t * 2)
        else:
            progress = (cycle_t - 16.0) / 6.0
            cx = 0.56 + progress * (0.97 - 0.56)

        foot_y = 0.74
        scale = 0.9 + 0.3 * foot_y
        w, h = 0.045 * scale, 0.20 * scale
        x1 = (cx - w / 2) * FRAME_WIDTH
        x2 = (cx + w / 2) * FRAME_WIDTH
        y2 = foot_y * FRAME_HEIGHT
        y1 = y2 - h * FRAME_HEIGHT
        return (x1, y1, x2, y2)

    def _car_position(self, t: float) -> tuple[float, float, float, float] | None:
        if t > 4.0:
            return None
        progress = t / 4.0
        cx = -0.1 + progress * 1.2
        cy = 0.44
        w, h = 0.12, 0.07
        x1 = (cx - w / 2) * FRAME_WIDTH
        x2 = (cx + w / 2) * FRAME_WIDTH
        y1 = (cy - h / 2) * FRAME_HEIGHT
        y2 = (cy + h / 2) * FRAME_HEIGHT
        return (x1, y1, x2, y2)

    @staticmethod
    def _draw_person(frame: np.ndarray, bbox: tuple[float, float, float, float]) -> None:
        x1, y1, x2, y2 = (int(v) for v in bbox)
        cx = (x1 + x2) // 2
        head_r = max(3, (x2 - x1) // 3)
        body_top = y1 + head_r * 2
        cv2.circle(frame, (cx, y1 + head_r), head_r, (210, 190, 170), -1)
        cv2.rectangle(frame, (x1, body_top), (x2, y2), (120, 90, 60), -1)

    @staticmethod
    def _draw_car(frame: np.ndarray, bbox: tuple[float, float, float, float]) -> None:
        x1, y1, x2, y2 = (int(v) for v in bbox)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (40, 40, 180), -1)
        wheel_y = y2 - 2
        for wx in (x1 + (x2 - x1) // 5, x2 - (x2 - x1) // 5):
            cv2.circle(frame, (wx, wheel_y), max(2, (x2 - x1) // 12), (20, 20, 20), -1)

    @staticmethod
    def _draw_hud(frame: np.ndarray, t: float) -> None:
        cv2.putText(frame, "SIMULATED DEMO FEED", (12, 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 220, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, time.strftime("%Y-%m-%d %H:%M:%S"), (12, FRAME_HEIGHT - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
