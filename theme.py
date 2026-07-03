"""Shared visual theme: color palette + injected CSS for the dashboard look
(dark-green sidebar nav, rounded white cards, pill buttons) used across every
page. Kept separate from app_state.py since this is pure presentation, not
session/resource glue.
"""

from __future__ import annotations

import streamlit as st

# -- palette --------------------------------------------------------------
SIDEBAR_BG = "#1F5C46"
SIDEBAR_BG_ACTIVE = "#2C7A5B"
SIDEBAR_TEXT = "#E7F1EC"
SIDEBAR_TEXT_MUTED = "#AFCABD"

PAGE_BG = "#EAF2EC"
CARD_BG = "#FFFFFF"

PRIMARY = "#2F8F68"
PRIMARY_DARK = "#1F5C46"
TEXT_DARK = "#1E2A24"
TEXT_MUTED = "#6B7B73"

# A small categorical palette anchored around the primary green, for charts
# that need more than one series (donuts, grouped bars).
CHART_PALETTE = ["#2F8F68", "#F0A45C", "#8B6FD1", "#5B9BD5", "#E0708A", "#4FB0A5"]

SEVERITY_COLORS = {"critical": "#E0708A", "warning": "#F0A45C", "info": "#5B9BD5"}


def inject_theme() -> None:
    """Injects the dashboard CSS. Call once near the top of streamlit_app.py —
    since st.navigation re-runs the entry script on every page, this applies
    globally without needing to be repeated in each page file."""
    st.markdown(
        f"""
        <style>
        /* -- sidebar: dark green nav, matching the dashboard reference -- */
        [data-testid="stSidebar"] {{
            background-color: {SIDEBAR_BG};
        }}
        [data-testid="stSidebar"] * {{
            color: {SIDEBAR_TEXT} !important;
        }}
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
            color: {SIDEBAR_TEXT_MUTED} !important;
        }}
        [data-testid="stSidebarNav"] a,
        [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {{
            border-radius: 10px;
            margin: 2px 8px;
        }}
        [data-testid="stSidebarNav"] a:hover,
        [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {{
            background-color: {SIDEBAR_BG_ACTIVE};
        }}
        [data-testid="stSidebarNav"] a[aria-current="page"],
        [data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] {{
            background-color: {SIDEBAR_BG_ACTIVE};
            font-weight: 600;
        }}
        [data-testid="stSidebar"] hr {{
            border-color: {SIDEBAR_BG_ACTIVE};
        }}

        /* -- main content -- */
        [data-testid="stMain"] {{
            background-color: {PAGE_BG};
        }}
        h1, h2, h3 {{
            color: {TEXT_DARK};
        }}

        /* -- rounded white "dashboard cards" --
        st.container(border=True) alone only gets a plain border with no fill
        in this Streamlit version (the border lives directly on the
        stVerticalBlock, which is otherwise transparent) — there's no stable
        test-id to hook for a background. Give every card container a
        key="card_..." and target the stable `st-key-card_*` class Streamlit
        derives from it instead. */
        [class*="st-key-card_"] {{
            background-color: {CARD_BG} !important;
            border-radius: 16px !important;
            box-shadow: 0 1px 3px rgba(30, 42, 36, 0.08);
        }}

        /* -- metric "stat card" look -- */
        [data-testid="stMetric"] {{
            background-color: {CARD_BG};
            border-radius: 14px;
            padding: 14px 16px;
            box-shadow: 0 1px 3px rgba(30, 42, 36, 0.08);
        }}
        [data-testid="stMetricValue"] {{
            color: {PRIMARY_DARK};
        }}

        /* -- pill-style buttons -- */
        .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
            border-radius: 999px;
        }}
        .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
            background-color: {PRIMARY};
            border-color: {PRIMARY};
        }}

        /* -- tabs, expanders, inputs: soften corners to match card style -- */
        [data-testid="stExpander"], .stTextInput input, .stNumberInput input,
        .stSelectbox [data-baseweb="select"] > div {{
            border-radius: 10px !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
