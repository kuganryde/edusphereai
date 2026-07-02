import time

from surveillance.alerts.engine import Alert
from surveillance.analytics.metrics import (
    activity_timeline,
    alerts_by_hour,
    alerts_by_zone,
    alerts_to_dataframe,
    class_distribution,
    frame_stats_to_dataframe,
)
from surveillance.storage.db import EventStore


def make_store(tmp_path) -> EventStore:
    return EventStore(tmp_path / "metrics.db")


def test_alerts_to_dataframe_empty():
    df = alerts_to_dataframe([])
    assert df.empty
    assert list(df.columns) == [
        "id", "timestamp", "camera_id", "alert_type", "severity",
        "object_class", "confidence", "zone", "message", "snapshot_path", "acknowledged",
    ]


def test_alerts_by_hour_matches_actual_alert_hours(tmp_path):
    store = make_store(tmp_path)
    store.log_alert(Alert(time.time(), "intrusion", "critical", "person", 0.9, "Gate", None, "a"), "CAM-01")
    store.log_alert(Alert(time.time(), "intrusion", "critical", "person", 0.9, "Gate", None, "b"), "CAM-01")

    df = alerts_to_dataframe(store.recent_alerts())
    by_hour = alerts_by_hour(df)

    assert len(by_hour) == 24
    assert by_hour["count"].sum() == 2
    current_hour = df["timestamp"].dt.hour.iloc[0]
    assert by_hour.loc[by_hour["hour"] == current_hour, "count"].iloc[0] == 2


def test_alerts_by_hour_empty_dataframe_has_24_zero_rows():
    df = alerts_to_dataframe([])
    by_hour = alerts_by_hour(df)
    assert len(by_hour) == 24
    assert (by_hour["count"] == 0).all()


def test_alerts_by_zone_groups_correctly(tmp_path):
    store = make_store(tmp_path)
    store.log_alert(Alert(time.time(), "intrusion", "critical", "person", 0.9, "Gate", None, "a"), "CAM-01")
    store.log_alert(Alert(time.time(), "intrusion", "critical", "person", 0.9, "Gate", None, "b"), "CAM-01")
    store.log_alert(Alert(time.time(), "intrusion", "critical", "person", 0.9, "Yard", None, "c"), "CAM-01")

    df = alerts_to_dataframe(store.recent_alerts())
    by_zone = alerts_by_zone(df)

    zone_counts = dict(zip(by_zone["zone"], by_zone["count"]))
    assert zone_counts == {"Gate": 2, "Yard": 1}


def test_frame_stats_and_class_distribution(tmp_path):
    store = make_store(tmp_path)
    store.log_frame_stats("CAM-01", {"person": 2, "car": 1}, backend="yolov8")
    store.log_frame_stats("CAM-01", {"person": 1}, backend="yolov8")

    frame_df = frame_stats_to_dataframe(store.frame_stats_since(0))
    dist = class_distribution(frame_df)

    counts = dict(zip(dist["class_name"], dist["count"]))
    assert counts == {"person": 3, "car": 1}


def test_activity_timeline_on_empty_data():
    empty_df = frame_stats_to_dataframe([])
    timeline = activity_timeline(empty_df)
    assert timeline.empty
