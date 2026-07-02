"""Live Monitor — the main CCTV dashboard: video feed with AI overlays,
live stats, and a rolling alert feed."""

from __future__ import annotations

import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import streamlit as st

from app_state import (
    SOURCE_DEMO,
    SOURCE_RTSP,
    SOURCE_TYPES,
    SOURCE_UPLOAD,
    SOURCE_WEBCAM,
    build_source,
    ensure_session_defaults,
    get_system,
    get_zones,
    save_snapshot,
    save_uploaded_video,
)
from surveillance.alerts.notifier import dispatch
from surveillance.utils.audio import generate_beep_wav
from surveillance.utils.drawing import draw_detections, draw_hud, draw_zones

ensure_session_defaults()
system = get_system()

st.title("🎥 Live Monitor")

backend_ok = system.detector.is_ai_backend
badge = "🟢 AI (YOLOv8)" if backend_ok else "🟡 Motion Detection (fallback)"
st.caption(f"Detection backend: **{badge}** — {system.detector.status_label}")
if not backend_ok and system.detector.load_error:
    with st.expander("Why am I in fallback mode?"):
        st.write(
            "The YOLOv8 weights couldn't be downloaded (no internet access to "
            "GitHub's release assets from this environment) or `ultralytics` "
            "isn't installed. The system automatically degraded to OpenCV "
            "background-subtraction motion detection so monitoring, zones, "
            "alerts, and logging all keep working. Once network access is "
            "available, just restart the app — YOLOv8 will load automatically."
        )
        st.code(system.detector.load_error, language="text")

if not system.alert_engine.is_armed():
    st.warning("System is **DISARMED** — detections still display, but no alerts will fire. "
               "Arm it from the Settings page.", icon="⚠️")

# -- source selection ---------------------------------------------------

with st.expander("📡 Video Source", expanded=not st.session_state.monitoring_active):
    st.session_state.source_type = st.selectbox(
        "Source", SOURCE_TYPES, index=SOURCE_TYPES.index(st.session_state.source_type),
        disabled=st.session_state.monitoring_active,
    )
    if st.session_state.source_type == SOURCE_UPLOAD:
        uploaded = st.file_uploader("Upload a video file (mp4/avi/mov)", type=["mp4", "avi", "mov", "mkv"],
                                     disabled=st.session_state.monitoring_active)
        if uploaded is not None:
            st.session_state.uploaded_video_path = save_uploaded_video(uploaded)
            st.success(f"Loaded: {uploaded.name}")
    elif st.session_state.source_type == SOURCE_WEBCAM:
        st.session_state.webcam_index = st.number_input(
            "Webcam device index", min_value=0, max_value=10,
            value=st.session_state.webcam_index, disabled=st.session_state.monitoring_active,
        )
        st.caption("Only works when this app runs directly on a machine with an attached camera.")
    elif st.session_state.source_type == SOURCE_RTSP:
        st.session_state.rtsp_url = st.text_input(
            "RTSP / HTTP camera URL", value=st.session_state.rtsp_url,
            placeholder="rtsp://user:pass@192.168.1.50:554/stream1",
            disabled=st.session_state.monitoring_active,
        )
    else:
        st.caption("A fully synthetic guard-house gate scene — no camera required. Great for "
                   "testing zones, alerts, and analytics end to end.")

# -- start / stop ---------------------------------------------------------

col1, col2, col3 = st.columns([1, 1, 3])
with col1:
    if st.button("▶ Start Monitoring", disabled=st.session_state.monitoring_active,
                  width="stretch", type="primary"):
        source = build_source(st.session_state.source_type)
        if source is not None:
            st.session_state.frame_source = source
            st.session_state.monitoring_active = True
            system.tracker.reset()
            st.rerun()
with col2:
    if st.button("⏹ Stop Monitoring", disabled=not st.session_state.monitoring_active,
                  width="stretch"):
        st.session_state.monitoring_active = False
        source = st.session_state.get("frame_source")
        if source is not None:
            source.release()
        st.session_state.frame_source = None
        st.rerun()

st.divider()

# -- live loop --------------------------------------------------------------

if st.session_state.monitoring_active and st.session_state.get("frame_source") is not None:
    source = st.session_state.frame_source
    zones = get_zones()

    video_col, side_col = st.columns([3, 1])
    with video_col:
        frame_placeholder = st.empty()
        stats_placeholder = st.empty()
    with side_col:
        st.markdown("##### 🚨 Live Alert Feed")
        alerts_placeholder = st.empty()
    audio_placeholder = st.empty()

    last_log_time = 0.0
    frame_times: deque[float] = deque(maxlen=30)
    beep_counter = 0

    while st.session_state.monitoring_active:
        frame = source.read()
        if frame is None:
            st.error(f"Lost connection to source: {source.label}. Stopping monitoring.")
            st.session_state.monitoring_active = False
            src = st.session_state.get("frame_source")
            if src is not None:
                src.release()
            st.session_state.frame_source = None
            st.rerun()
            break

        t0 = time.time()
        st.session_state["last_frame"] = frame

        simulated = source.simulated_detections()
        detections = simulated if simulated is not None else system.detector.infer(frame)
        system.tracker.update(detections)

        h, w = frame.shape[:2]
        alerts = system.alert_engine.evaluate(detections, zones, w, h, system.tracker)

        for alert in alerts:
            snapshot_path = None
            if alert.severity in ("critical", "warning"):
                snapshot_path = save_snapshot(frame, alert)
            system.store.log_alert(alert, system.settings.camera_id, snapshot_path)
            dispatch(system.settings, alert)
            st.session_state.recent_alerts.insert(0, alert)
        st.session_state.recent_alerts = st.session_state.recent_alerts[:30]

        class_counts: dict[str, int] = {}
        for det in detections:
            class_counts[det.class_name] = class_counts.get(det.class_name, 0) + 1
        now = time.time()
        if now - last_log_time > 1.0:
            system.store.log_frame_stats(system.settings.camera_id, class_counts, system.detector.backend)
            last_log_time = now

        display = draw_zones(frame.copy(), zones, system.alert_engine.is_armed())
        display = draw_detections(display, detections)
        frame_times.append(now)
        fps = (len(frame_times) - 1) / (frame_times[-1] - frame_times[0]) if len(frame_times) > 1 else 0.0
        display = draw_hud(
            display, site_name=system.settings.site_name, camera_id=system.settings.camera_id,
            armed=system.alert_engine.is_armed(), backend_label=system.detector.status_label,
            object_count=len(detections), fps=fps,
        )

        frame_placeholder.image(cv2.cvtColor(display, cv2.COLOR_BGR2RGB), width="stretch")

        with stats_placeholder.container():
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Objects in Frame", len(detections))
            m2.metric("Active Tracks", system.tracker.active_count())
            m3.metric("Session Alerts", len(st.session_state.recent_alerts))
            m4.metric("FPS", f"{fps:.1f}")

        with alerts_placeholder.container():
            if not st.session_state.recent_alerts:
                st.caption("No alerts yet. Monitoring…")
            else:
                for a in st.session_state.recent_alerts[:10]:
                    icon = {"critical": "🔴", "warning": "🟠", "info": "🔵"}.get(a.severity, "⚪")
                    st.markdown(f"{icon} `{time.strftime('%H:%M:%S', time.localtime(a.ts))}`  \n{a.message}")

        if alerts and system.settings.sound_alerts and any(a.severity in ("critical", "warning") for a in alerts):
            beep_counter += 1
            # st.audio has no `key` param, and Streamlit's auto-generated element ID is
            # derived from the audio bytes themselves — so identical cached beep bytes
            # across loop iterations collide as "duplicate" elements. A per-alert pitch
            # jitter (inaudible-ish, 950-980Hz) keeps every call's byte content unique.
            freq = 950.0 + (beep_counter % 30)
            audio_placeholder.audio(generate_beep_wav(freq=freq), format="audio/wav", autoplay=True)

        elapsed = time.time() - t0
        time.sleep(max(0.0, (1 / 12) - elapsed))
else:
    st.info("Configure a video source above and click **Start Monitoring** to begin.")
