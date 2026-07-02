from surveillance.video.stream import FRAME_HEIGHT, FRAME_WIDTH, DemoSource


def test_demo_source_produces_correctly_sized_frames():
    source = DemoSource()
    frame = source.read()
    assert frame is not None
    assert frame.shape == (FRAME_HEIGHT, FRAME_WIDTH, 3)


def test_demo_source_is_always_connected():
    source = DemoSource()
    assert source.is_connected is True


def test_demo_source_simulated_detections_have_valid_bboxes():
    # The car/person animations intentionally enter and exit off-screen, so
    # bboxes may briefly extend past frame bounds — only shape/ordering and
    # metadata are guaranteed.
    source = DemoSource()
    for _ in range(5):
        source.read()
    detections = source.simulated_detections()
    assert detections is not None
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        assert x1 < x2
        assert y1 < y2
        assert det.class_name in ("person", "car")
        assert 0.0 <= det.confidence <= 1.0
