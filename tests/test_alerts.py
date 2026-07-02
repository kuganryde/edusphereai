from surveillance.alerts.engine import AlertEngine
from surveillance.config import Settings
from surveillance.detection.tracker import CentroidTracker
from surveillance.types import Detection
from surveillance.zones import Zone

FULL_FRAME_ZONE = Zone(
    name="Gate", points=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
    kind="restricted", classes=["person"],
)


def make_engine(**overrides) -> AlertEngine:
    defaults = dict(loiter_seconds=10.0, crowd_threshold=3, alert_cooldown_seconds=20.0)
    defaults.update(overrides)
    return AlertEngine(Settings(**defaults))


def test_intrusion_alert_fires_for_restricted_zone():
    engine = make_engine()
    tracker = CentroidTracker()
    det = Detection("person", 0.9, (10, 10, 30, 50))
    tracker.update([det])

    alerts = engine.evaluate([det], [FULL_FRAME_ZONE], 100, 100, tracker)

    assert any(a.alert_type == "intrusion" for a in alerts)


def test_no_alerts_when_disarmed():
    engine = make_engine(armed=False)
    tracker = CentroidTracker()
    det = Detection("person", 0.9, (10, 10, 30, 50))
    tracker.update([det])

    alerts = engine.evaluate([det], [FULL_FRAME_ZONE], 100, 100, tracker)

    assert alerts == []


def test_cooldown_suppresses_repeat_intrusion_alerts(monkeypatch):
    engine = make_engine()
    tracker = CentroidTracker()
    det = Detection("person", 0.9, (10, 10, 30, 50))
    tracker.update([det])

    # A mutable fake clock: patching the (shared) `time` module affects every
    # caller of time.time(), including CentroidTracker, so a fixed clock
    # value avoids coupling the test to exactly how many times each collaborator
    # happens to call it per evaluate().
    clock = {"t": 1000.0}
    monkeypatch.setattr("surveillance.alerts.engine.time.time", lambda: clock["t"])

    first = engine.evaluate([det], [FULL_FRAME_ZONE], 100, 100, tracker)
    clock["t"] = 1005.0  # 5s later, still within the 20s cooldown window
    second = engine.evaluate([det], [FULL_FRAME_ZONE], 100, 100, tracker)

    assert any(a.alert_type == "intrusion" for a in first)
    assert not any(a.alert_type == "intrusion" for a in second)  # within cooldown window


def test_loitering_alert_after_dwell_threshold(monkeypatch):
    engine = make_engine(loiter_seconds=10.0)
    tracker = CentroidTracker()
    det = Detection("person", 0.9, (10, 10, 30, 50))
    tracker.update([det])
    tid = det.track_id

    # Simulate the track having already dwelled 15s in the zone.
    tracker.set_zone(tid, "Gate", now=1000.0)
    tracker.set_zone(tid, "Gate", now=1015.0)

    monkeypatch.setattr("surveillance.alerts.engine.time.time", lambda: 1015.0)
    alerts = engine.evaluate([det], [FULL_FRAME_ZONE], 100, 100, tracker)

    assert any(a.alert_type == "loitering" for a in alerts)


def test_crowd_alert_when_threshold_exceeded():
    engine = make_engine(crowd_threshold=2)
    tracker = CentroidTracker()
    dets = [
        Detection("person", 0.9, (10, 10, 30, 50)),
        Detection("person", 0.9, (400, 400, 420, 440)),
    ]
    tracker.update(dets)

    alerts = engine.evaluate(dets, [], 1000, 1000, tracker)

    assert any(a.alert_type == "crowd" for a in alerts)


def test_threat_object_flagged_regardless_of_zone():
    engine = make_engine()
    tracker = CentroidTracker()
    det = Detection("knife", 0.7, (5, 5, 15, 15))
    tracker.update([det])

    alerts = engine.evaluate([det], [], 100, 100, tracker)

    assert any(a.alert_type == "threat_object" for a in alerts)
