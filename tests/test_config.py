from surveillance.config import Settings, load_settings, save_settings


def test_settings_dict_round_trip():
    settings = Settings(site_name="Front Gate", crowd_threshold=7)
    restored = Settings.from_dict(settings.as_dict())
    assert restored == settings


def test_settings_from_dict_ignores_unknown_keys():
    restored = Settings.from_dict({"site_name": "Test", "not_a_real_field": 123})
    assert restored.site_name == "Test"


def test_save_and_load_settings(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr("surveillance.config.SETTINGS_PATH", settings_path)
    monkeypatch.setattr("surveillance.config.DATA_DIR", tmp_path)

    settings = Settings(site_name="Back Gate", loiter_seconds=42.0)
    save_settings(settings)
    loaded = load_settings()

    assert loaded.site_name == "Back Gate"
    assert loaded.loiter_seconds == 42.0


def test_load_settings_returns_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("surveillance.config.SETTINGS_PATH", tmp_path / "missing.json")
    monkeypatch.setattr("surveillance.config.DATA_DIR", tmp_path)

    loaded = load_settings()
    assert loaded == Settings()
