"""Zone Editor — define restricted / watch polygons over a snapshot of the camera feed."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
import pandas as pd
import streamlit as st

from app_state import ensure_session_defaults, get_zones, persist_zones
from surveillance.config import COCO_CLASSES, DEFAULT_SECURITY_CLASSES
from surveillance.video.stream import DemoSource
from surveillance.zones import Zone

ensure_session_defaults()

st.title("🗺️ Zone Editor")
st.caption(
    "Define restricted areas (e.g. a gate lane or fence line) over a snapshot of the camera view. "
    "Anyone entering a **restricted** zone triggers an intrusion alert; **watch** zones only "
    "track loitering/occupancy without alerting on entry."
)

# -- background snapshot ----------------------------------------------------


def _get_background_frame() -> np.ndarray:
    last = st.session_state.get("last_frame")
    if last is not None:
        return last
    demo = DemoSource()
    return demo.read()


col_a, col_b = st.columns([1, 3])
with col_a:
    if st.button("🔄 Refresh Snapshot"):
        st.session_state.pop("zone_bg_frame", None)
if "zone_bg_frame" not in st.session_state:
    st.session_state["zone_bg_frame"] = _get_background_frame()
with col_b:
    st.caption("Uses the last frame seen on Live Monitor, or a fresh demo-scene snapshot if you "
               "haven't started monitoring yet.")

bg_frame = st.session_state["zone_bg_frame"]
zones = get_zones()

tab_rect, tab_manual, tab_manage = st.tabs(["🔲 Quick Rectangle Zone", "🔢 Precise Coordinates", "📋 Manage Zones"])

with tab_rect:
    st.markdown("Drag the sliders to position a rectangular zone — the preview updates live.")
    sc1, sc2 = st.columns(2)
    x1, x2 = sc1.slider("Left / Right (x)", 0.0, 1.0, (0.35, 0.65), 0.01, key="rect_x")
    y1, y2 = sc2.slider("Top / Bottom (y)", 0.0, 1.0, (0.45, 0.85), 0.01, key="rect_y")

    preview = bg_frame.copy()
    h, w = preview.shape[:2]
    px1, py1, px2, py2 = int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)
    overlay = preview.copy()
    cv2.rectangle(overlay, (px1, py1), (px2, py2), (60, 60, 255), -1)
    preview = cv2.addWeighted(overlay, 0.3, preview, 0.7, 0)
    cv2.rectangle(preview, (px1, py1), (px2, py2), (60, 60, 255), 2)
    st.image(cv2.cvtColor(preview, cv2.COLOR_BGR2RGB), caption="Preview", width="stretch")

    name = st.text_input("Zone name", value=f"Zone {len(zones) + 1}", key="rect_zone_name")
    kind = st.selectbox("Zone type", ["restricted", "watch"], key="rect_zone_kind",
                         help="Restricted = intrusion alerts on entry. Watch = loitering/occupancy only.")
    classes = st.multiselect("Classes to monitor in this zone", COCO_CLASSES,
                              default=DEFAULT_SECURITY_CLASSES[:3], key="rect_zone_classes")

    if st.button("💾 Save This Zone", type="primary", key="save_rect_zone"):
        if x2 - x1 < 0.02 or y2 - y1 < 0.02:
            st.error("The rectangle is too small — widen it first.")
        elif not name.strip():
            st.error("Give the zone a name.")
        elif not classes:
            st.error("Select at least one class to monitor.")
        else:
            points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            color = (60, 60, 255) if kind == "restricted" else (200, 200, 60)
            zones.append(Zone(name=name.strip(), points=points, kind=kind, classes=classes, color=color))
            persist_zones(zones)
            st.success(f"Saved zone '{name.strip()}'.")
            st.rerun()

with tab_manual:
    st.markdown("For non-rectangular zones, enter normalized vertex coordinates "
                "(0.0–1.0, relative to frame width/height) directly.")
    default_df = pd.DataFrame({"x": [0.3, 0.6, 0.6, 0.3], "y": [0.5, 0.5, 0.8, 0.8]})
    vertex_df = st.data_editor(default_df, num_rows="dynamic", key="manual_vertex_editor",
                                width="stretch")

    preview = bg_frame.copy()
    pts = [(row.x, row.y) for row in vertex_df.itertuples() if 0 <= row.x <= 1 and 0 <= row.y <= 1]
    if len(pts) >= 3:
        h, w = preview.shape[:2]
        poly_px = np.array([(int(x * w), int(y * h)) for x, y in pts], dtype=np.int32)
        overlay = preview.copy()
        cv2.fillPoly(overlay, [poly_px], (60, 200, 60))
        preview = cv2.addWeighted(overlay, 0.3, preview, 0.7, 0)
        cv2.polylines(preview, [poly_px], True, (60, 200, 60), 2)
    st.image(cv2.cvtColor(preview, cv2.COLOR_BGR2RGB), caption="Preview", width="stretch")

    m_name = st.text_input("Zone name", value=f"Zone {len(zones) + 1}", key="manual_zone_name")
    m_kind = st.selectbox("Zone type", ["restricted", "watch"], key="manual_zone_kind")
    m_classes = st.multiselect("Classes to monitor", COCO_CLASSES, default=DEFAULT_SECURITY_CLASSES[:3],
                                key="manual_zone_classes")

    if st.button("💾 Save Manual Zone", type="primary", key="save_manual_zone"):
        if len(pts) < 3:
            st.error("Enter at least 3 valid (x, y) vertices between 0 and 1.")
        elif not m_name.strip():
            st.error("Give the zone a name.")
        elif not m_classes:
            st.error("Select at least one class to monitor.")
        else:
            color = (60, 60, 255) if m_kind == "restricted" else (200, 200, 60)
            zones.append(Zone(name=m_name.strip(), points=pts, kind=m_kind, classes=m_classes, color=color))
            persist_zones(zones)
            st.success(f"Saved zone '{m_name.strip()}'.")
            st.rerun()

with tab_manage:
    if not zones:
        st.info("No zones defined yet. Add one from the other tabs.")
    else:
        preview = bg_frame.copy()
        h, w = preview.shape[:2]
        overlay = preview.copy()
        for zone in zones:
            poly_px = np.array(zone.to_pixels(w, h), dtype=np.int32)
            color = zone.color if zone.kind == "restricted" else (150, 150, 60)
            cv2.fillPoly(overlay, [poly_px], color)
        preview = cv2.addWeighted(overlay, 0.25, preview, 0.75, 0)
        for zone in zones:
            poly_px = np.array(zone.to_pixels(w, h), dtype=np.int32)
            color = zone.color if zone.kind == "restricted" else (150, 150, 60)
            cv2.polylines(preview, [poly_px], True, color, 2)
            cv2.putText(preview, zone.name.encode("ascii", "replace").decode("ascii"), tuple(poly_px[0]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        st.image(cv2.cvtColor(preview, cv2.COLOR_BGR2RGB), width="stretch")

        for i, zone in enumerate(zones):
            c1, c2, c3, c4 = st.columns([3, 2, 3, 1])
            c1.markdown(f"**{zone.name}**")
            c2.markdown(f"`{zone.kind}`")
            c3.caption(", ".join(zone.classes))
            if c4.button("🗑️", key=f"delete_zone_{i}"):
                zones.pop(i)
                persist_zones(zones)
                st.rerun()
