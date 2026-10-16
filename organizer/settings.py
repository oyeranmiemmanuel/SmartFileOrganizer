"""Remembered user settings (appearance, last folders, scan options).

Settings are a convenience, never critical: a missing or damaged file simply
gives the defaults. The folder below is provisional and matches the history
folder chosen in Phase 2; Phase 5 finalises where application data lives.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

APP_DIR_NAME = "SmartFileOrganizer"
SETTINGS_VERSION = 1
APPEARANCE_MODES = ("Light", "Dark", "System")
UI_SCALES = (90, 100, 110, 125, 150)


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / APP_DIR_NAME


def default_settings_path() -> Path:
    return app_data_dir() / "settings.json"


def default_rules_path() -> Path:
    return app_data_dir() / "rules.json"


def default_log_dir() -> Path:
    return app_data_dir() / "logs"


@dataclass
class Settings:
    appearance: str = "System"
    ui_scale: int = 100
    source: str = ""
    destination: str = ""
    destination_custom: bool = False  # False: the destination follows the source
    recursive: bool = False
    include_hidden: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"version": SETTINGS_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, data: Any) -> "Settings":
        """Build settings from parsed JSON, replacing any invalid value by its default."""
        defaults = cls()
        if not isinstance(data, dict):
            return defaults
        values: dict[str, Any] = {}
        for item in fields(cls):
            default = getattr(defaults, item.name)
            value = data.get(item.name, default)
            if isinstance(default, bool):
                valid = isinstance(value, bool)
            elif isinstance(default, int):
                valid = isinstance(value, int) and not isinstance(value, bool)
            else:
                valid = isinstance(value, str)
            values[item.name] = value if valid else default
        settings = cls(**values)
        if settings.appearance not in APPEARANCE_MODES:
            settings.appearance = defaults.appearance
        if settings.ui_scale not in UI_SCALES:
            settings.ui_scale = defaults.ui_scale
        return settings


class SettingsStore:
    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path else default_settings_path()

    def load(self) -> Settings:
        try:
            text = self.path.read_text(encoding="utf-8-sig")
            return Settings.from_dict(json.loads(text))
        except (OSError, ValueError):  # missing, unreadable, or not valid JSON
            return Settings()

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".tmp")
        temp.write_text(json.dumps(settings.to_dict(), indent=2) + "\n", encoding="utf-8")
        os.replace(temp, self.path)