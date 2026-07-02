"""Central configuration and persisted settings for SentryVision AI."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
MODELS_DIR = DATA_DIR / "models"
DB_PATH = DATA_DIR / "sentryvision.db"
ZONES_PATH = DATA_DIR / "zones.json"
SETTINGS_PATH = DATA_DIR / "settings.json"

# COCO class names understood by the bundled YOLOv8 model, in class-index order.
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

# Classes that are meaningfully "security relevant" for a guard/sentry post.
# Kept as the default detection filter so the model isn't wasting cycles
# (and cluttering the UI) flagging houseplants and toasters.
DEFAULT_SECURITY_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "bus", "truck",
    "backpack", "handbag", "suitcase", "knife", "scissors", "dog",
]

# Classes treated as "weapon-adjacent" for elevated-severity alerts. Stock
# COCO has no firearm class; a custom-trained model would be required for
# true weapon detection (see PRD "Known Limitations").
THREAT_CLASSES = {"knife", "scissors"}

VEHICLE_CLASSES = {"bicycle", "car", "motorcycle", "bus", "truck"}


@dataclasses.dataclass
class Settings:
    """User-tunable, persisted configuration for the surveillance system."""

    site_name: str = "Guard House - Main Gate"
    camera_id: str = "CAM-01"

    model_name: str = "yolov8n.pt"
    confidence_threshold: float = 0.45
    iou_threshold: float = 0.45
    detection_classes: list[str] = dataclasses.field(
        default_factory=lambda: list(DEFAULT_SECURITY_CLASSES)
    )
    inference_width: int = 640
    frame_skip: int = 1  # run inference on every Nth frame

    loiter_seconds: float = 12.0
    crowd_threshold: int = 5
    alert_cooldown_seconds: float = 20.0

    armed: bool = True
    schedule_enabled: bool = False
    armed_start_hour: int = 18  # 24h clock, e.g. dusk
    armed_end_hour: int = 6

    sound_alerts: bool = True
    webhook_enabled: bool = False
    webhook_url: str = ""
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""

    retention_days: int = 30

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        valid = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    ensure_dirs()
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text())
            return Settings.from_dict(data)
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    return Settings()


def save_settings(settings: Settings) -> None:
    ensure_dirs()
    SETTINGS_PATH.write_text(json.dumps(settings.as_dict(), indent=2))
