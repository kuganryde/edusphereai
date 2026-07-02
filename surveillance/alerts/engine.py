"""Rule-based alert engine: intrusion, loitering, crowding, and flagged objects.

Runs entirely on the outputs of the detector + tracker — no extra model
inference. Each rule is cooldown-gated per (rule, zone/track) key so a
person standing still in a restricted zone doesn't spam a hundred identical
alerts a minute.
"""

from __future__ import annotations

import dataclasses
import time
from datetime import datetime

from surveillance.config import Settings, THREAT_CLASSES
from surveillance.detection.tracker import CentroidTracker
from surveillance.types import Detection
from surveillance.zones import Zone, bbox_feet_point, point_in_polygon


@dataclasses.dataclass
class Alert:
    ts: float
    alert_type: str  # "intrusion" | "loitering" | "crowd" | "threat_object"
    severity: str  # "info" | "warning" | "critical"
    object_class: str
    confidence: float
    zone: str | None
    bbox: tuple[float, float, float, float] | None
    message: str
    track_id: int | None = None


class AlertEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cooldowns: dict[str, float] = {}

    def is_armed(self, now: datetime | None = None) -> bool:
        if not self.settings.armed:
            return False
        if not self.settings.schedule_enabled:
            return True
        now = now or datetime.now()
        start, end = self.settings.armed_start_hour, self.settings.armed_end_hour
        if start == end:
            return True
        hour = now.hour
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end  # schedule wraps past midnight

    def _cooldown_ok(self, key: str, now: float) -> bool:
        last = self._cooldowns.get(key)
        if last is not None and now - last < self.settings.alert_cooldown_seconds:
            return False
        self._cooldowns[key] = now
        return True

    def evaluate(
        self,
        detections: list[Detection],
        zones: list[Zone],
        frame_width: int,
        frame_height: int,
        tracker: CentroidTracker,
    ) -> list[Alert]:
        now = time.time()
        alerts: list[Alert] = []
        armed = self.is_armed()
        zone_polygons = {zone.name: zone.to_pixels(frame_width, frame_height) for zone in zones}

        person_like_count = sum(1 for d in detections if d.class_name in ("person", "motion"))

        for det in detections:
            foot = bbox_feet_point(det.bbox)
            matched_zone: Zone | None = None
            for zone in zones:
                if det.class_name in zone.classes and point_in_polygon(foot, zone_polygons[zone.name]):
                    matched_zone = zone
                    break
            det.zone = matched_zone.name if matched_zone else None

            dwell = 0.0
            if det.track_id is not None:
                dwell = tracker.set_zone(det.track_id, det.zone, now)

            if det.class_name in THREAT_CLASSES:
                key = f"threat:{det.class_name}:{det.zone}"
                if self._cooldown_ok(key, now):
                    alerts.append(Alert(
                        now, "threat_object", "critical", det.class_name, det.confidence,
                        det.zone, det.bbox,
                        f"Flagged object detected: {det.class_name}"
                        + (f" in '{det.zone}'" if det.zone else ""),
                        det.track_id,
                    ))

            if armed and matched_zone is not None and matched_zone.kind == "restricted":
                key = f"intrusion:{matched_zone.name}:{det.track_id or det.class_name}"
                if self._cooldown_ok(key, now):
                    alerts.append(Alert(
                        now, "intrusion", "critical", det.class_name, det.confidence,
                        matched_zone.name, det.bbox,
                        f"{det.class_name.title()} entered restricted zone '{matched_zone.name}'",
                        det.track_id,
                    ))

            if armed and det.zone and dwell >= self.settings.loiter_seconds:
                key = f"loiter:{det.zone}:{det.track_id}"
                if self._cooldown_ok(key, now):
                    alerts.append(Alert(
                        now, "loitering", "warning", det.class_name, det.confidence,
                        det.zone, det.bbox,
                        f"{det.class_name.title()} loitering in '{det.zone}' for {dwell:.0f}s",
                        det.track_id,
                    ))

        if armed and person_like_count >= self.settings.crowd_threshold:
            if self._cooldown_ok("crowd", now):
                alerts.append(Alert(
                    now, "crowd", "warning", "person", 1.0, None, None,
                    f"Crowd detected: {person_like_count} people in frame",
                ))

        return alerts
