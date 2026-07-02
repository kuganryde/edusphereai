from surveillance.config import Settings
from surveillance.system import SurveillanceSystem


def test_build_wires_all_components(tmp_path, monkeypatch):
    monkeypatch.setattr("surveillance.config.DB_PATH", tmp_path / "db.sqlite3")
    monkeypatch.setattr("surveillance.storage.db.DB_PATH", tmp_path / "db.sqlite3")

    settings = Settings(model_name="definitely-not-a-real-model.pt")
    system = SurveillanceSystem.build(settings)

    assert system.detector.backend == "motion"
    assert system.alert_engine.settings is system.settings
    assert system.tracker.active_count() == 0
    system.store.close()


def test_apply_settings_updates_thresholds_without_model_reload(tmp_path, monkeypatch):
    monkeypatch.setattr("surveillance.storage.db.DB_PATH", tmp_path / "db.sqlite3")

    settings = Settings(model_name="definitely-not-a-real-model.pt", confidence_threshold=0.4)
    system = SurveillanceSystem.build(settings)
    original_detector = system.detector

    new_settings = Settings(model_name="definitely-not-a-real-model.pt", confidence_threshold=0.7)
    system.apply_settings(new_settings)

    assert system.detector is original_detector  # same model, no reload
    assert system.detector.confidence_threshold == 0.7
    assert system.settings.confidence_threshold == 0.7
    system.store.close()
