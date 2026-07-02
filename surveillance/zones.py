"""Restricted / watch zones: polygon geometry, persistence, and containment tests."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from surveillance.config import ZONES_PATH, ensure_dirs

ZONE_KINDS = ("restricted", "watch")


@dataclasses.dataclass
class Zone:
    """A polygon drawn on the camera frame, stored in normalized (0..1) coordinates
    so it stays valid regardless of the source video's resolution."""

    name: str
    points: list[tuple[float, float]]  # normalized (x, y), 0..1
    kind: str = "restricted"  # "restricted" -> intrusion alerts, "watch" -> loiter/count only
    classes: list[str] = dataclasses.field(default_factory=lambda: ["person"])
    color: tuple[int, int, int] = (255, 60, 60)  # BGR

    def to_pixels(self, width: int, height: int) -> list[tuple[int, int]]:
        return [(int(x * width), int(y * height)) for x, y in self.points]

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Zone":
        return cls(
            name=data["name"],
            points=[tuple(p) for p in data["points"]],
            kind=data.get("kind", "restricted"),
            classes=data.get("classes", ["person"]),
            color=tuple(data.get("color", (255, 60, 60))),
        )


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Standard ray-casting point-in-polygon test. Works on any consistent
    coordinate system (normalized or pixel), as long as point and polygon match."""
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    n = len(polygon)
    x1, y1 = polygon[0]
    for i in range(1, n + 1):
        x2, y2 = polygon[i % n]
        if y > min(y1, y2):
            if y <= max(y1, y2):
                if x <= max(x1, x2):
                    if y1 != y2:
                        x_intersect = (y - y1) * (x2 - x1) / (y2 - y1) + x1
                    else:
                        x_intersect = x1
                    if x1 == x2 or x <= x_intersect:
                        inside = not inside
        x1, y1 = x2, y2
    return inside


def bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def bbox_feet_point(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    """Bottom-center of a bounding box — a better proxy than the centroid for
    'where a person is standing' when checking ground-plane zone membership."""
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, y2


def load_zones(path: Path | None = None) -> list[Zone]:
    ensure_dirs()
    path = path or ZONES_PATH
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
        return [Zone.from_dict(z) for z in raw]
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return []


def save_zones(zones: list[Zone], path: Path | None = None) -> None:
    ensure_dirs()
    path = path or ZONES_PATH
    path.write_text(json.dumps([z.as_dict() for z in zones], indent=2))
