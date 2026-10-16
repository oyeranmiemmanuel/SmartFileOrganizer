import sys

import smart_file_organizer as launcher


def test_say_never_fails_without_a_console(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    launcher._say("hello")  # must not raise


def test_log_location_follows_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert launcher._log_path() == tmp_path / "SmartFileOrganizer" / "logs" / "launcher.log"


def test_write_log_appends(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    first = launcher._write_log("first problem")
    launcher._write_log("second problem")
    text = first.read_text(encoding="utf-8")
    assert "first problem" in text and "second problem" in text


def test_legacy_flag_uses_the_classic_interface(monkeypatch):
    monkeypatch.setattr(launcher, "_run_legacy", lambda: 7)
    assert launcher.main(["--legacy"]) == 7


def test_version_flag(capsys):
    assert launcher.main(["--version"]) == 0
    assert "Smart File Organizer" in capsys.readouterr().out