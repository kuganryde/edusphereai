"""SentryVision AI — entry point.

A pure-Python, AI-powered CCTV surveillance platform for guard house and
sentry post deployments: real-time computer-vision object detection,
zone-based intrusion/loitering alerts, event logging, and analytics — all
running through a single Streamlit application.
"""

from __future__ import annotations

import streamlit as st

from theme import inject_theme

st.set_page_config(
    page_title="SentryVision AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

live_monitor = st.Page("pages/1_live_monitor.py", title="Live Monitor", icon="🎥", default=True)
zone_editor = st.Page("pages/2_zone_editor.py", title="Zone Editor", icon="🗺️")
event_log = st.Page("pages/3_event_log.py", title="Event Log", icon="🚨")
analytics = st.Page("pages/4_analytics.py", title="Analytics", icon="📊")
settings_page = st.Page("pages/5_settings.py", title="Settings", icon="⚙️")

nav = st.navigation(
    {
        "Monitoring": [live_monitor, zone_editor],
        "Insights": [event_log, analytics],
        "System": [settings_page],
    }
)

with st.sidebar:
    st.markdown("## 🛡️ SentryVision AI")
    st.caption("AI CCTV for guard & sentry houses")
    st.divider()

nav.run()
