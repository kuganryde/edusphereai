"""A lightweight centroid-based multi-object tracker.

Not a full Kalman/Hungarian-assignment tracker (e.g. ByteTrack/DeepSORT) —
intentionally simple, dependency-free, and fast enough for CPU real-time use
on a guard-house workstation. It exists to give each detection a stable
``track_id`` across frames so the alert engine can measure *dwell time*
inside a zone (loitering) rather than just single-frame presence.
"""

from __future__ import annotations

import dataclasses
import time

import numpy as np

from surveillance.types import Detection
from surveillance.zones import bbox_feet_point


@dataclasses.dataclass
class _Track:
    track_id: int
    class_name: str
    centroid: tuple[float, float]
    disappeared: int = 0
    first_seen: float = dataclasses.field(default_factory=time.time)
    last_seen: float = dataclasses.field(default_factory=time.time)
    current_zone: str | None = None
    zone_since: float | None = None


class CentroidTracker:
    def __init__(self, max_disappeared: int = 20, max_distance: float = 90.0) -> None:
        self._next_id = 1
        self.tracks: dict[int, _Track] = {}
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance

    def reset(self) -> None:
        self._next_id = 1
        self.tracks.clear()

    def update(self, detections: list[Detection]) -> list[Detection]:
        """Assign a ``track_id`` to each detection (mutates in place) and
        return the same list for convenience."""
        now = time.time()

        if not detections:
            for t in list(self.tracks.values()):
                t.disappeared += 1
                if t.disappeared > self.max_disappeared:
                    del self.tracks[t.track_id]
            return detections

        centroids = [bbox_feet_point(d.bbox) for d in detections]

        if not self.tracks:
            for det, c in zip(detections, centroids):
                self._register(det, c, now)
            return detections

        track_ids = list(self.tracks.keys())
        track_centroids = np.array([self.tracks[tid].centroid for tid in track_ids])
        det_centroids = np.array(centroids)
        distances = np.linalg.norm(
            track_centroids[:, None, :] - det_centroids[None, :, :], axis=2
        )

        candidates = [
            (distances[i, j], i, j)
            for i in range(distances.shape[0])
            for j in range(distances.shape[1])
        ]
        candidates.sort(key=lambda c: c[0])

        assigned_tracks: set[int] = set()
        assigned_dets: set[int] = set()
        for dist, i, j in candidates:
            if i in assigned_tracks or j in assigned_dets or dist > self.max_distance:
                continue
            tid = track_ids[i]
            if self.tracks[tid].class_name != detections[j].class_name:
                continue
            self._update_track(tid, detections[j], centroids[j], now)
            assigned_tracks.add(i)
            assigned_dets.add(j)

        for j, (det, c) in enumerate(zip(detections, centroids)):
            if j not in assigned_dets:
                self._register(det, c, now)

        for i, tid in enumerate(track_ids):
            if i not in assigned_tracks:
                t = self.tracks[tid]
                t.disappeared += 1
                if t.disappeared > self.max_disappeared:
                    del self.tracks[tid]

        return detections

    def _register(self, det: Detection, centroid: tuple[float, float], now: float) -> None:
        tid = self._next_id
        self._next_id += 1
        self.tracks[tid] = _Track(
            track_id=tid, class_name=det.class_name, centroid=centroid,
            last_seen=now, first_seen=now,
        )
        det.track_id = tid

    def _update_track(self, tid: int, det: Detection, centroid: tuple[float, float], now: float) -> None:
        t = self.tracks[tid]
        t.centroid = centroid
        t.last_seen = now
        t.disappeared = 0
        det.track_id = tid

    def set_zone(self, track_id: int, zone_name: str | None, now: float | None = None) -> float:
        """Record which zone a track currently occupies. Returns the
        continuous dwell time (seconds) in that zone — 0 if it just entered,
        changed zones, or isn't in one."""
        now = now if now is not None else time.time()
        t = self.tracks.get(track_id)
        if t is None:
            return 0.0
        if zone_name != t.current_zone:
            t.current_zone = zone_name
            t.zone_since = now if zone_name else None
            return 0.0
        if zone_name is None or t.zone_since is None:
            return 0.0
        return now - t.zone_since

    def active_count(self) -> int:
        return len(self.tracks)
