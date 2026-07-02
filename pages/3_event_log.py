"""Event Log — searchable history of alerts with snapshot review and acknowledgment."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app_state import ensure_session_defaults, get_system
from surveillance.analytics.metrics import alerts_to_dataframe

ensure_session_defaults()
system = get_system()

st.title("🚨 Event Log")

counts = system.store.total_counts()
c1, c2, c3 = st.columns(3)
c1.metric("Total Alerts", counts["alerts"])
c2.metric("Unacknowledged", counts["unacknowledged"])
c3.metric("Frames Logged", counts["frames_logged"])

st.divider()

filter_col1, filter_col2, filter_col3 = st.columns(3)
with filter_col1:
    type_filter = st.multiselect("Alert type", ["intrusion", "loitering", "crowd", "threat_object"])
with filter_col2:
    only_unack = st.checkbox("Unacknowledged only")
with filter_col3:
    limit = st.slider("Max rows", 10, 500, 100, step=10)

rows = system.store.recent_alerts(
    limit=limit,
    alert_types=type_filter or None,
    unacknowledged_only=only_unack,
)
df = alerts_to_dataframe(rows)

if df.empty:
    st.info("No alerts recorded yet. Start monitoring on the Live Monitor page to generate events.")
else:
    for _, row in df.iterrows():
        icon = {"critical": "🔴", "warning": "🟠", "info": "🔵"}.get(row["severity"], "⚪")
        ack = "✅" if row["acknowledged"] else "⬜"
        with st.expander(
            f"{icon} {ack} `{row['timestamp']:%Y-%m-%d %H:%M:%S}` — {row['alert_type'].title()} — {row['message']}"
        ):
            info_col, img_col = st.columns([2, 1])
            with info_col:
                st.write(f"**Object:** {row['object_class']}  (confidence {row['confidence']:.0%})")
                st.write(f"**Zone:** {row['zone'] or 'n/a'}")
                st.write(f"**Camera:** {row['camera_id']}")
                st.write(f"**Severity:** {row['severity']}")
                if not row["acknowledged"]:
                    if st.button("Acknowledge", key=f"ack_{row['id']}"):
                        system.store.acknowledge_alert(int(row["id"]))
                        st.rerun()
            with img_col:
                if row["snapshot_path"] and Path(row["snapshot_path"]).exists():
                    st.image(row["snapshot_path"], width="stretch")
                else:
                    st.caption("No snapshot saved for this alert.")

    st.divider()
    st.download_button(
        "⬇ Export as CSV",
        data=df.drop(columns=["snapshot_path"]).to_csv(index=False).encode("utf-8"),
        file_name=f"sentryvision_alerts_{time.strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )
