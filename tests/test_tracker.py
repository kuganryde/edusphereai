from surveillance.detection.tracker import CentroidTracker
from surveillance.types import Detection


def test_same_object_keeps_track_id_across_frames():
    tracker = CentroidTracker()
    frame1 = [Detection("person", 0.9, (10, 10, 30, 50))]
    frame2 = [Detection("person", 0.9, (12, 11, 32, 51))]  # small movement

    tracker.update(frame1)
    tid1 = frame1[0].track_id
    tracker.update(frame2)
    tid2 = frame2[0].track_id

    assert tid1 is not None
    assert tid1 == tid2


def test_far_away_detection_gets_new_track_id():
    tracker = CentroidTracker(max_distance=50)
    frame1 = [Detection("person", 0.9, (10, 10, 30, 50))]
    frame2 = [Detection("person", 0.9, (500, 500, 520, 540))]

    tracker.update(frame1)
    tid1 = frame1[0].track_id
    tracker.update(frame2)
    tid2 = frame2[0].track_id

    assert tid1 != tid2


def test_different_class_does_not_merge_tracks():
    tracker = CentroidTracker(max_distance=1000)
    frame1 = [Detection("person", 0.9, (10, 10, 30, 50))]
    frame2 = [Detection("car", 0.9, (12, 11, 32, 51))]

    tracker.update(frame1)
    tid1 = frame1[0].track_id
    tracker.update(frame2)
    tid2 = frame2[0].track_id

    assert tid1 != tid2


def test_track_disappears_after_max_disappeared_frames():
    tracker = CentroidTracker(max_disappeared=2)
    frame1 = [Detection("person", 0.9, (10, 10, 30, 50))]
    tracker.update(frame1)
    assert tracker.active_count() == 1

    tracker.update([])
    tracker.update([])
    tracker.update([])
    assert tracker.active_count() == 0


def test_set_zone_dwell_time_accumulates_and_resets():
    tracker = CentroidTracker()
    frame = [Detection("person", 0.9, (10, 10, 30, 50))]
    tracker.update(frame)
    tid = frame[0].track_id

    dwell = tracker.set_zone(tid, "gate", now=100.0)
    assert dwell == 0.0  # just entered

    dwell = tracker.set_zone(tid, "gate", now=115.0)
    assert dwell == 15.0

    dwell = tracker.set_zone(tid, None, now=120.0)
    assert dwell == 0.0  # left the zone

    dwell = tracker.set_zone(tid, "gate", now=121.0)
    assert dwell == 0.0  # re-entered, dwell resets
