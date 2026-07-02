"""Turn EventStore rows into pandas DataFrames ready for Plotly charts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import pandas as pd


def alerts_to_dataframe(rows: list[sqlite3.Row]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=[
            "id", "timestamp", "camera_id", "alert_type", "severity",
            "object_class", "confidence", "zone", "message", "snapshot_path", "acknowledged",
        ])
    records = []
    for row in rows:
        records.append({
            "id": row["id"],
            "timestamp": datetime.fromtimestamp(row["ts"]),
            "camera_id": row["camera_id"],
            "alert_type": row["alert_type"],
            "severity": row["severity"],
            "object_class": row["object_class"],
            "confidence": row["confidence"],
            "zone": row["zone"],
            "message": row["message"],
            "snapshot_path": row["snapshot_path"],
            "acknowledged": bool(row["acknowledged"]),
        })
    return pd.DataFrame.from_records(records)


def frame_stats_to_dataframe(rows: list[sqlite3.Row]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["timestamp", "camera_id", "total_objects", "backend", "class_counts"])
    records = []
    for row in rows:
        records.append({
            "timestamp": datetime.fromtimestamp(row["ts"]),
            "camera_id": row["camera_id"],
            "total_objects": row["total_objects"],
            "backend": row["backend"],
            "class_counts": json.loads(row["class_counts_json"]),
        })
    return pd.DataFrame.from_records(records)


def activity_timeline(frame_df: pd.DataFrame, freq: str = "1min") -> pd.DataFrame:
    if frame_df.empty:
        return pd.DataFrame(columns=["timestamp", "total_objects"])
    ts = frame_df.set_index("timestamp")["total_objects"].resample(freq).mean().fillna(0)
    return ts.reset_index()


def class_distribution(frame_df: pd.DataFrame) -> pd.DataFrame:
    if frame_df.empty:
        return pd.DataFrame(columns=["class_name", "count"])
    counts: dict[str, int] = {}
    for cc in frame_df["class_counts"]:
        for cls, n in cc.items():
            counts[cls] = counts.get(cls, 0) + n
    if not counts:
        return pd.DataFrame(columns=["class_name", "count"])
    return (
        pd.DataFrame(sorted(counts.items(), key=lambda kv: -kv[1]), columns=["class_name", "count"])
    )


def alerts_by_hour(alerts_df: pd.DataFrame) -> pd.DataFrame:
    full = pd.DataFrame({"hour": range(24)})
    if alerts_df.empty:
        full["count"] = 0
        return full
    counts = alerts_df["timestamp"].dt.hour.value_counts()
    # .map() matches on the Series' index values directly, sidestepping the
    # column-naming quirks of value_counts().reset_index() across pandas versions.
    full["count"] = full["hour"].map(counts).fillna(0).astype(int)
    return full


def alerts_by_zone(alerts_df: pd.DataFrame) -> pd.DataFrame:
    if alerts_df.empty:
        return pd.DataFrame(columns=["zone", "count"])
    df = alerts_df.dropna(subset=["zone"])
    if df.empty:
        return pd.DataFrame(columns=["zone", "count"])
    return df.groupby("zone").size().reset_index(name="count").sort_values("count", ascending=False)
