"""Streamlit-facing glue: cached resources and session-state helpers shared
by the entry point and every page. Kept separate from the `surveillance`
package so the backend stays framework-agnostic and unit-testable without
importing Streamlit at all.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from surveillance.alerts.engine import Alert
from surveillance.config import SNAPSHOT_DIR, Settings, load_settings, save_settings
from surveillance.system import SurveillanceSystem
from surveillance.video.stream import DemoSource, FileSource, FrameSource, RTSPSource, WebcamSource
from surveillance.zones import Zone, load_zones, save_zones

SOURCE_DEMO = "Demo Scene (simulated)"
SOURCE_UPLOAD = "Uploaded Video File"
SOURCE_WEBCAM = "Local Webcam"
SOURCE_RTSP = "IP Camera / RTSP"
SOURCE_TYPES = [SOURCE_DEMO, SOURCE_UPLOAD, SOURCE_WEBCAM, SOURCE_RTSP]


@st.cache_resource(show_spinner="Starting SentryVision AI engine…")
def get_system() -> SurveillanceSystem:
    return SurveillanceSystem.build(load_settings())


def update_settings(new_settings: Settings) -> None:
    save_settings(new_settings)
    get_system().apply_settings(new_settings)


def get_zones() -> list[Zone]:
    if "zones" not in st.session_state:
        st.session_state["zones"] = load_zones()
    return st.session_state["zones"]


def persist_zones(zones: list[Zone]) -> None:
    save_zones(zones)
    st.session_state["zones"] = zones


def ensure_session_defaults() -> None:
    st.session_state.setdefault("monitoring_active", False)
    st.session_state.setdefault("source_type", SOURCE_DEMO)
    st.session_state.setdefault("frame_counter", 0)
    st.session_state.setdefault("recent_alerts", [])
    st.session_state.setdefault("uploaded_video_path", None)
    st.session_state.setdefault("rtsp_url", "")
    st.session_state.setdefault("webcam_index", 0)


def build_source(source_type: str) -> FrameSource | None:
    """Instantiate the right FrameSource for the current session's selection.
    Returns None (with a UI error) if the source can't be opened."""
    if source_type == SOURCE_DEMO:
        return DemoSource()

    if source_type == SOURCE_UPLOAD:
        path = st.session_state.get("uploaded_video_path")
        if not path:
            st.warning("Upload a video file below to start monitoring it.")
            return None
        return FileSource(path)

    if source_type == SOURCE_WEBCAM:
        source = WebcamSource(st.session_state.get("webcam_index", 0))
        if not source.is_connected:
            st.error(
                "No local webcam detected on this machine. This is expected when "
                "running in a hosted/cloud environment — use the Demo Scene, an "
                "uploaded video, or an RTSP/IP camera URL instead."
            )
            return None
        return source

    if source_type == SOURCE_RTSP:
        url = st.session_state.get("rtsp_url", "").strip()
        if not url:
            st.warning("Enter an RTSP/HTTP camera URL below to start monitoring it.")
            return None
        source = RTSPSource(url)
        if not source.is_connected:
            st.error(f"Could not connect to camera stream: {url}")
            return None
        return source

    return None


def save_uploaded_video(uploaded_file) -> str:
    """Persist an uploaded video to a temp file and return its path."""
    suffix = Path(uploaded_file.name).suffix or ".mp4"
    tmp_dir = Path(tempfile.gettempdir()) / "sentryvision_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dest = tmp_dir / f"upload_{abs(hash(uploaded_file.name))}{suffix}"
    dest.write_bytes(uploaded_file.getbuffer())
    return str(dest)


def save_snapshot(frame: np.ndarray, alert: Alert) -> str:
    ensure_dir = SNAPSHOT_DIR
    ensure_dir.mkdir(parents=True, exist_ok=True)
    ts_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(alert.ts))
    ms = int((alert.ts % 1) * 1000)
    fname = f"{alert.alert_type}_{ts_str}_{ms:03d}.jpg"
    path = ensure_dir / fname
    cv2.imwrite(str(path), frame)
    return str(path)
