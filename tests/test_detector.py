import numpy as np

from surveillance.detection.detector import ObjectDetector


def test_falls_back_to_motion_when_model_unavailable():
    detector = ObjectDetector(model_name="definitely-not-a-real-model.pt")
    assert detector.backend == "motion"
    assert detector.is_ai_backend is False
    assert detector.load_error is not None


def test_motion_backend_never_raises_on_blank_frames():
    detector = ObjectDetector(model_name="definitely-not-a-real-model.pt")
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for _ in range(25):
        detections = detector.infer(frame)
    assert detections == []  # steady blank scene -> nothing detected once warmed up


def test_motion_backend_detects_a_new_bright_region():
    detector = ObjectDetector(model_name="definitely-not-a-real-model.pt")
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for _ in range(25):
        detector.infer(frame)

    moving_frame = frame.copy()
    moving_frame[50:150, 50:150] = 255
    detections = detector.infer(moving_frame)

    assert len(detections) >= 1
    assert detections[0].class_name == "motion"


def test_infer_on_none_frame_returns_empty_list():
    detector = ObjectDetector(model_name="definitely-not-a-real-model.pt")
    assert detector.infer(None) == []
