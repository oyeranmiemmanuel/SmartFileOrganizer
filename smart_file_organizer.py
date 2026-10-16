"""Smart File Organizer launcher.

Starts the CustomTkinter interface. The previous interface is kept as
``legacy_app.py``: run it with ``--legacy``, or it opens automatically when
CustomTkinter is not installed. ``--version`` prints the version.

This file also runs inside the packaged (windowed) executable, which has no
console, so it never assumes that printing works and writes problems to a log.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _say(message: str) -> None:
    """Print, but never fail: sys.stdout is None in a windowed executable."""
    try:
        print(message)
    except Exception:
        pass


def _log_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "SmartFileOrganizer" / "logs" / "launcher.log"


def _write_log(text: str) -> Path | None:
    path = _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text.rstrip() + "\n\n")
    except OSError:
        return None
    return path


def _show_notice(message: str, error: bool = False) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        show = messagebox.showerror if error else messagebox.showwarning
        show("Smart File Organizer", message)
        root.destroy()
    except Exception:
        pass


def _run_legacy() -> int:
    try:
        import legacy_app
    except ImportError:
        _say("legacy_app.py was not found next to this file.")
        return 1
    legacy_app.main()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--version" in args:
        from organizer import __version__

        _say(f"Smart File Organizer {__version__}")
        return 0
    if "--legacy" in args:
        return _run_legacy()
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        message = (
            "CustomTkinter is not installed, so the new interface cannot start.\n\n"
            "Install it with:\n    python -m pip install -r requirements.txt\n\n"
            "The classic version will open instead."
        )
        _say(message)
        _show_notice(message)
        return _run_legacy()
    try:
        from organizer.app import run

        return run()
    except Exception:
        details = traceback.format_exc()
        log = _write_log(details)
        where = f"\n\nDetails were written to:\n{log}" if log else ""
        _say(details)
        _show_notice(f"Smart File Organizer could not start.{where}", error=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())