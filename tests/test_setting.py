import json

from organizer.settings import (
    APP_DIR_NAME,
    Settings,
    SettingsStore,
    app_data_dir,
    default_rules_path,
    default_settings_path,
)


def test_missing_file_gives_defaults(tmp_path):
    assert SettingsStore(tmp_path / "none.json").load() == Settings()


def test_round_trip_and_no_temp_file_left(tmp_path):
    store = SettingsStore(tmp_path / "sub" / "settings.json")
    settings = Settings(
        appearance="Dark", ui_scale=125, source="C:\\a", destination="C:\\b",
        destination_custom=True, recursive=True, include_hidden=True,
    )
    store.save(settings)
    assert store.load() == settings
    assert not list((tmp_path / "sub").glob("*.tmp"))
    assert json.loads(store.path.read_text(encoding="utf-8"))["version"] == 1


def test_invalid_values_fall_back_to_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps(
            {"appearance": "Purple", "ui_scale": 7, "recursive": "yes", "source": 5, "include_hidden": True}
        ),
        encoding="utf-8",
    )
    loaded = SettingsStore(path).load()
    defaults = Settings()
    assert loaded.appearance == defaults.appearance
    assert loaded.ui_scale == defaults.ui_scale
    assert loaded.recursive is False
    assert loaded.source == ""
    assert loaded.include_hidden is True


def test_corrupt_and_non_object_files_give_defaults(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    assert SettingsStore(bad).load() == Settings()
    listing = tmp_path / "list.json"
    listing.write_text("[1, 2]", encoding="utf-8")
    assert SettingsStore(listing).load() == Settings()


def test_data_locations_follow_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert app_data_dir() == tmp_path / APP_DIR_NAME
    assert default_settings_path() == tmp_path / APP_DIR_NAME / "settings.json"
    assert default_rules_path() == tmp_path / APP_DIR_NAME / "rules.json"


def test_data_location_without_localappdata(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert app_data_dir().name == APP_DIR_NAME