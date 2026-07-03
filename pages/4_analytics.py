"""Analytics — dashboard-style overview: stat cards, activity trends, class
distribution, and alert patterns."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import plotly.express as px
import plotly.graph_objects as go
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
from theme import CHART_PALETTE, PRIMARY, SEVERITY_COLORS, TEXT_MUTED

ensure_session_defaults()
system = get_system()


def _ring_chart(pct: float, color: str) -> go.Figure:
    """A percentage "progress ring" donut, echoing the dashboard reference's
    circular stat widgets."""
    pct = max(0.0, min(100.0, pct))
    fig = go.Figure(go.Pie(
        values=[pct, 100 - pct],
        hole=0.72,
        # Track color needs to read clearly against the white card background —
        # the page's mint background tone is too close to white for that.
        marker=dict(colors=[color, "#DCE5DF"]),
        textinfo="none",
        sort=False,
        direction="clockwise",
    ))
    fig.update_layout(
        showlegend=False, height=180, margin=dict(l=0, r=0, t=0, b=0),
        annotations=[dict(text=f"{pct:.0f}%", x=0.5, y=0.5, font=dict(size=22, color=color), showarrow=False)],
    )
    return fig


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

    st.write("")

    left, right = st.columns([2, 1])
    with left, st.container(border=True, key="card_activity"):
        st.markdown("#### Activity Over Time")
        timeline = activity_timeline(frame_df)
        if timeline.empty:
            st.caption("No frame activity in this window.")
        else:
            fig = px.line(timeline, x="timestamp", y="total_objects", markers=True,
                           color_discrete_sequence=[PRIMARY])
            fig.update_traces(fill="tozeroy", fillcolor="rgba(47, 143, 104, 0.12)")
            fig.update_layout(yaxis_title="Avg objects/frame", xaxis_title="", height=300,
                               margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width="stretch")

    with right, st.container(border=True, key="card_class_dist"):
        st.markdown("#### Detections by Class")
        dist = class_distribution(frame_df)
        if dist.empty:
            st.caption("No class data in this window.")
        else:
            fig = px.bar(dist.head(8), x="class_name", y="count", color_discrete_sequence=[PRIMARY])
            fig.update_layout(xaxis_title="", yaxis_title="Count", height=300,
                               margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width="stretch")

    st.write("")

    st.markdown("#### At a Glance")
    total_alerts = len(alerts_df)
    total_frames = len(frame_df)
    ack_pct = 100.0 * alerts_df["acknowledged"].mean() if total_alerts else 0.0
    critical_pct = 100.0 * critical_n / total_alerts if total_alerts else 0.0
    ai_coverage_pct = (
        100.0 * (frame_df["backend"] == "yolov8").mean() if total_frames else 0.0
    )

    r1, r2, r3 = st.columns(3)
    for col, key, label, pct, color in (
        (r1, "card_ring_ack", "Alerts Acknowledged", ack_pct, CHART_PALETTE[0]),
        (r2, "card_ring_critical", "Critical Alert Share", critical_pct, CHART_PALETTE[1]),
        (r3, "card_ring_ai", "AI Detection Coverage", ai_coverage_pct, CHART_PALETTE[3]),
    ):
        with col, st.container(border=True, key=key):
            st.plotly_chart(_ring_chart(pct, color), width="stretch", config={"displayModeBar": False})
            st.markdown(f"<div style='text-align:center;color:{TEXT_MUTED}'>{label}</div>",
                        unsafe_allow_html=True)

    st.write("")

    left2, right2 = st.columns(2)
    with left2, st.container(border=True, key="card_by_hour"):
        st.markdown("#### Alerts by Hour of Day")
        by_hour = alerts_by_hour(alerts_df)
        if by_hour.empty or by_hour["count"].sum() == 0:
            st.caption("No alerts in this window.")
        else:
            fig = px.bar(by_hour, x="hour", y="count", color_discrete_sequence=[PRIMARY])
            fig.update_layout(xaxis_title="Hour (0-23)", yaxis_title="Alerts", height=300,
                               margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width="stretch")

    with right2, st.container(border=True, key="card_top_zones"):
        st.markdown("#### Top Zones by Alerts")
        by_zone = alerts_by_zone(alerts_df)
        if by_zone.empty:
            st.caption("No zone-tagged alerts in this window.")
        else:
            chart_col, list_col = st.columns([1, 1])
            with chart_col:
                fig = px.pie(by_zone, names="zone", values="count", hole=0.55,
                              color_discrete_sequence=CHART_PALETTE)
                fig.update_layout(height=260, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
                st.plotly_chart(fig, width="stretch")
            with list_col:
                for i, row in enumerate(by_zone.head(5).itertuples(), start=1):
                    st.markdown(
                        f"<div style='display:flex;justify-content:space-between;padding:4px 0'>"
                        f"<span>{i}. {row.zone}</span><b>{row.count}</b></div>",
                        unsafe_allow_html=True,
                    )

    if not alerts_df.empty:
        st.write("")
        with st.container(border=True, key="card_severity"):
            st.markdown("#### Alert Severity Breakdown")
            sev_counts = alerts_df["severity"].value_counts().reset_index()
            sev_counts.columns = ["severity", "count"]
            fig = px.bar(sev_counts, x="severity", y="count", color="severity",
                         color_discrete_map=SEVERITY_COLORS)
            fig.update_layout(height=260, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width="stretch")
