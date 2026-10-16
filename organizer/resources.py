"""Locating bundled files (such as the icon), from source or from the packaged executable."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running as a PyInstaller executable."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Folder holding bundled data: PyInstaller's extraction folder, or the project folder.

    Bundled files are READ-ONLY (a one-file build unpacks them to a temporary
    folder). Anything the app writes belongs in the per-user data folder
    (see settings.app_data_dir).
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    return bundle_root() / relative


def app_icon_path() -> Path | None:
    path = resource_path("assets/icon.ico")
    return path if path.is_file() else None