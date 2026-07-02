"""Analytics — activity trends, class distribution, and alert patterns."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import plotly.express as px
import streamlit as st

from app_state import ensure_session_defaults, get_system
from surveillance.analytics.metrics import (
    activity_timeline,
    alerts_by_hour,
    alerts_by_zone,
    alerts_to_dataframe,
    class_distribution,
    frame_stats_to_dataframe,
)

ensure_session_defaults()
system = get_system()

st.title("📊 Analytics")

window_label = st.selectbox("Time window", ["Last hour", "Last 24 hours", "Last 7 days", "All time"], index=1)
window_seconds = {"Last hour": 3600, "Last 24 hours": 86400, "Last 7 days": 604800, "All time": None}[window_label]
since_ts = time.time() - window_seconds if window_seconds else 0.0

frame_rows = system.store.frame_stats_since(since_ts)
alert_rows = system.store.recent_alerts(limit=5000, since_ts=since_ts)

frame_df = frame_stats_to_dataframe(frame_rows)
alerts_df = alerts_to_dataframe(alert_rows)

if frame_df.empty and alerts_df.empty:
    st.info("No activity recorded yet for this window. Run the Live Monitor to generate data.")
else:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Detections Logged (frames)", len(frame_df))
    c2.metric("Total Alerts", len(alerts_df))
    critical_n = int((alerts_df["severity"] == "critical").sum()) if not alerts_df.empty else 0
    c3.metric("Critical Alerts", critical_n)
    avg_objects = f"{frame_df['total_objects'].mean():.1f}" if not frame_df.empty else "0"
    c4.metric("Avg Objects / Frame", avg_objects)

    st.divider()

    left, right = st.columns(2)
    with left:
        st.markdown("#### Activity Over Time")
        timeline = activity_timeline(frame_df)
        if timeline.empty:
            st.caption("No frame activity in this window.")
        else:
            fig = px.line(timeline, x="timestamp", y="total_objects", markers=True)
            fig.update_layout(yaxis_title="Avg objects/frame", xaxis_title="", height=320)
            st.plotly_chart(fig, width="stretch")

    with right:
        st.markdown("#### Detections by Class")
        dist = class_distribution(frame_df)
        if dist.empty:
            st.caption("No class data in this window.")
        else:
            fig = px.bar(dist.head(12), x="class_name", y="count")
            fig.update_layout(xaxis_title="", yaxis_title="Count", height=320)
            st.plotly_chart(fig, width="stretch")

    left2, right2 = st.columns(2)
    with left2:
        st.markdown("#### Alerts by Hour of Day")
        by_hour = alerts_by_hour(alerts_df)
        if by_hour.empty or by_hour["count"].sum() == 0:
            st.caption("No alerts in this window.")
        else:
            fig = px.bar(by_hour, x="hour", y="count")
            fig.update_layout(xaxis_title="Hour (0-23)", yaxis_title="Alerts", height=320)
            st.plotly_chart(fig, width="stretch")

    with right2:
        st.markdown("#### Alerts by Zone")
        by_zone = alerts_by_zone(alerts_df)
        if by_zone.empty:
            st.caption("No zone-tagged alerts in this window.")
        else:
            fig = px.pie(by_zone, names="zone", values="count", hole=0.45)
            fig.update_layout(height=320)
            st.plotly_chart(fig, width="stretch")

    if not alerts_df.empty:
        st.markdown("#### Alert Severity Breakdown")
        sev_counts = alerts_df["severity"].value_counts().reset_index()
        sev_counts.columns = ["severity", "count"]
        fig = px.bar(sev_counts, x="severity", y="count", color="severity",
                     color_discrete_map={"critical": "#e0245e", "warning": "#f5a623", "info": "#4a90d9"})
        fig.update_layout(height=280, showlegend=False)
        st.plotly_chart(fig, width="stretch")
