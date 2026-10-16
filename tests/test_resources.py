import sys
from pathlib import Path

import organizer.resources as resources


def test_bundle_root_in_a_packaged_app(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resources.bundle_root() == tmp_path
    assert resources.resource_path("assets/icon.ico") == tmp_path / "assets" / "icon.ico"


def test_icon_is_found_when_present(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resources.app_icon_path() is None
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "icon.ico").write_bytes(b"icon")
    assert resources.app_icon_path() == tmp_path / "assets" / "icon.ico"


def test_bundle_root_from_source(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    expected = Path(resources.__file__).resolve().parent.parent
    assert resources.bundle_root() == expected


def test_is_frozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert resources.is_frozen() is False
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert resources.is_frozen() is True