import time

from surveillance.alerts.engine import Alert
from surveillance.storage.db import EventStore


def make_store(tmp_path):
    return EventStore(tmp_path / "test.db")


def test_log_and_read_alert(tmp_path):
    store = make_store(tmp_path)
    alert = Alert(time.time(), "intrusion", "critical", "person", 0.9, "Gate", (1, 2, 3, 4), "test message")

    alert_id = store.log_alert(alert, camera_id="CAM-01", snapshot_path="/tmp/snap.jpg")
    assert alert_id > 0

    rows = store.recent_alerts()
    assert len(rows) == 1
    assert rows[0]["alert_type"] == "intrusion"
    assert rows[0]["zone"] == "Gate"
    assert rows[0]["acknowledged"] == 0


def test_acknowledge_alert(tmp_path):
    store = make_store(tmp_path)
    alert = Alert(time.time(), "loitering", "warning", "person", 0.5, "Gate", None, "loitering")
    alert_id = store.log_alert(alert, camera_id="CAM-01")

    store.acknowledge_alert(alert_id)
    rows = store.recent_alerts(unacknowledged_only=True)
    assert rows == []

    all_rows = store.recent_alerts()
    assert all_rows[0]["acknowledged"] == 1


def test_filter_by_alert_type(tmp_path):
    store = make_store(tmp_path)
    store.log_alert(Alert(time.time(), "intrusion", "critical", "person", 0.9, None, None, "a"), "CAM-01")
    store.log_alert(Alert(time.time(), "crowd", "warning", "person", 0.9, None, None, "b"), "CAM-01")

    rows = store.recent_alerts(alert_types=["crowd"])
    assert len(rows) == 1
    assert rows[0]["alert_type"] == "crowd"


def test_frame_stats_logging_and_query(tmp_path):
    store = make_store(tmp_path)
    store.log_frame_stats("CAM-01", {"person": 2, "car": 1}, backend="yolov8")

    rows = store.frame_stats_since(0)
    assert len(rows) == 1
    assert rows[0]["total_objects"] == 3
    assert rows[0]["backend"] == "yolov8"


def test_purge_older_than(tmp_path):
    store = make_store(tmp_path)
    old_alert = Alert(time.time() - 100 * 86400, "intrusion", "critical", "person", 0.9, None, None, "old")
    new_alert = Alert(time.time(), "intrusion", "critical", "person", 0.9, None, None, "new")
    store.log_alert(old_alert, "CAM-01")
    store.log_alert(new_alert, "CAM-01")

    purged = store.purge_older_than(days=30)
    assert purged == 1
    remaining = store.recent_alerts()
    assert len(remaining) == 1
    assert remaining[0]["message"] == "new"


def test_alert_counts_by_type(tmp_path):
    store = make_store(tmp_path)
    store.log_alert(Alert(time.time(), "intrusion", "critical", "person", 0.9, None, None, "a"), "CAM-01")
    store.log_alert(Alert(time.time(), "intrusion", "critical", "person", 0.9, None, None, "b"), "CAM-01")
    store.log_alert(Alert(time.time(), "crowd", "warning", "person", 0.9, None, None, "c"), "CAM-01")

    counts = store.alert_counts_by_type()
    assert counts == {"intrusion": 2, "crowd": 1}
