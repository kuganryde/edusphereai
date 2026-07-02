"""AI object detection engine.

Primary backend is Ultralytics YOLOv8 (state-of-the-art single-shot CNN
detector, pure-Python API, CPU or GPU). If the model can't be loaded — no
`ultralytics`/`torch` installed, or no network access on first run to fetch
weights — the detector transparently degrades to an OpenCV background
subtraction motion detector so the surveillance pipeline (zones, alerts,
logging) keeps working end to end. The active backend is always surfaced to
the UI so operators know exactly what's running.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from surveillance.config import COCO_CLASSES, MODELS_DIR, ensure_dirs
from surveillance.types import Detection

logger = logging.getLogger(__name__)

# Ultralytics' own download retry/backoff has no reliable cross-thread
# timeout (it can hang indefinitely on a blocked/unreachable host when run
# outside the main thread — exactly the situation inside a Streamlit
# ScriptRunner). We enforce our own bound so the UI never freezes on a
# first-run weight download; if it's not done in time we fall back to
# motion detection immediately and let the AI backend activate on next
# restart once/if the weights become reachable.
MODEL_LOAD_TIMEOUT_SECONDS = 12.0


class ObjectDetector:
    backend: str  # "yolov8" | "motion" | "unavailable"
    load_error: str | None

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        confidence_threshold: float = 0.45,
        iou_threshold: float = 0.45,
        classes_of_interest: list[str] | None = None,
    ) -> None:
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.classes_of_interest = classes_of_interest or []
        self.load_error = None

        self._model: Any = None
        self._bg_subtractor: Any = None
        self.backend = "unavailable"

        self._load_yolo()
        if self.backend != "yolov8":
            self._load_motion_fallback()

    # -- backend setup -----------------------------------------------------

    def _load_yolo(self) -> None:
        try:
            from ultralytics import YOLO  # local import: heavy, optional dependency
        except ImportError as exc:
            self.load_error = f"ultralytics not installed ({exc})"
            return

        ensure_dirs()
        weights_path = self.model_name
        if not Path(weights_path).is_absolute():
            weights_path = str(MODELS_DIR / self.model_name)

        outcome: dict[str, Any] = {}

        def _attempt() -> None:
            try:
                outcome["model"] = YOLO(weights_path)
            except Exception as exc:  # weight download failure, corrupt cache, etc.
                outcome["error"] = exc

        # Run on a worker thread and bound it with .join(timeout=...) rather
        # than a signal-based timeout, since this constructor may itself be
        # running off the main thread (e.g. inside Streamlit).
        loader = threading.Thread(target=_attempt, daemon=True)
        loader.start()
        loader.join(timeout=MODEL_LOAD_TIMEOUT_SECONDS)

        if loader.is_alive():
            self.load_error = (
                f"timed out after {MODEL_LOAD_TIMEOUT_SECONDS:.0f}s fetching {self.model_name} "
                "(no network access to the weight host). The download will keep retrying in the "
                "background; restart the app once network access is available."
            )
            return
        if "model" in outcome:
            self._model = outcome["model"]
            self.backend = "yolov8"
        else:
            self.load_error = f"could not load {self.model_name}: {outcome.get('error')}"

    def _load_motion_fallback(self) -> None:
        self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300, varThreshold=32, detectShadows=True
        )
        self._motion_warmup_frames = 20  # MOG2 floods the frame with "motion" until it learns the scene
        self.backend = "motion"

    @property
    def is_ai_backend(self) -> bool:
        return self.backend == "yolov8"

    @property
    def status_label(self) -> str:
        if self.backend == "yolov8":
            return f"YOLOv8 AI Detector ({self.model_name})"
        if self.backend == "motion":
            return "Motion Detection (fallback - AI model unavailable)"
        return "Detector unavailable"

    def _class_indices(self) -> list[int] | None:
        if not self.classes_of_interest:
            return None
        wanted = set(self.classes_of_interest)
        return [i for i, name in enumerate(COCO_CLASSES) if name in wanted]

    # -- inference -----------------------------------------------------------

    def infer(self, frame: np.ndarray) -> list[Detection]:
        if frame is None:
            return []
        if self.backend == "yolov8":
            return self._infer_yolo(frame)
        if self.backend == "motion":
            return self._infer_motion(frame)
        return []

    def _infer_yolo(self, frame: np.ndarray) -> list[Detection]:
        try:
            results = self._model.predict(
                source=frame,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                classes=self._class_indices(),
                verbose=False,
            )
        except Exception as exc:
            logger.warning("YOLO inference failed, falling back to motion: %s", exc)
            self.load_error = str(exc)
            self._load_motion_fallback()
            return self._infer_motion(frame)

        detections: list[Detection] = []
        if not results:
            return detections
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return detections
        names = result.names
        for box in boxes:
            xyxy = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            class_name = names.get(cls_id, str(cls_id)) if isinstance(names, dict) else str(cls_id)
            detections.append(Detection(class_name=class_name, confidence=conf, bbox=tuple(xyxy)))
        return detections

    def _infer_motion(self, frame: np.ndarray) -> list[Detection]:
        mask = self._bg_subtractor.apply(frame)
        if self._motion_warmup_frames > 0:
            self._motion_warmup_frames -= 1
            return []
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.dilate(mask, np.ones((7, 7), np.uint8), iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        frame_area = frame.shape[0] * frame.shape[1]
        min_area = max(400, int(frame_area * 0.003))
        detections: list[Detection] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            detections.append(
                Detection(class_name="motion", confidence=min(0.99, area / (frame_area * 0.15)),
                          bbox=(float(x), float(y), float(x + w), float(y + h)))
            )
        return detections
