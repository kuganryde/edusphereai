"""Wires the detector, tracker, alert engine, and event store into one
long-lived object the UI layer can hold onto across Streamlit reruns."""

from __future__ import annotations

import dataclasses

from surveillance.alerts.engine import AlertEngine
from surveillance.config import Settings
from surveillance.detection.detector import ObjectDetector
from surveillance.detection.tracker import CentroidTracker
from surveillance.storage.db import EventStore


@dataclasses.dataclass
class SurveillanceSystem:
    settings: Settings
    detector: ObjectDetector
    tracker: CentroidTracker
    alert_engine: AlertEngine
    store: EventStore

    @classmethod
    def build(cls, settings: Settings) -> "SurveillanceSystem":
        detector = ObjectDetector(
            model_name=settings.model_name,
            confidence_threshold=settings.confidence_threshold,
            iou_threshold=settings.iou_threshold,
            classes_of_interest=settings.detection_classes,
        )
        return cls(
            settings=settings,
            detector=detector,
            tracker=CentroidTracker(),
            alert_engine=AlertEngine(settings),
            store=EventStore(),
        )

    def apply_settings(self, settings: Settings) -> None:
        """Push updated settings into every component; only reloads the
        (expensive) detection model if the model name actually changed."""
        model_changed = settings.model_name != self.settings.model_name
        self.settings = settings
        self.alert_engine.settings = settings
        if model_changed:
            self.detector = ObjectDetector(
                model_name=settings.model_name,
                confidence_threshold=settings.confidence_threshold,
                iou_threshold=settings.iou_threshold,
                classes_of_interest=settings.detection_classes,
            )
        else:
            self.detector.confidence_threshold = settings.confidence_threshold
            self.detector.iou_threshold = settings.iou_threshold
            self.detector.classes_of_interest = settings.detection_classes
