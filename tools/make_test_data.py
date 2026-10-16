"""Create a disposable folder of sample files for trying Smart File Organizer.

Usage (from the project folder):
    python tools/make_test_data.py [target_folder]
    python tools/make_test_data.py [target_folder] --reset

The default target is  Desktop\\SFO_TestData . The files you scan are in its
"Downloads" subfolder. Nothing outside the target folder is touched. --reset
deletes and recreates the target, but ONLY if it was created by this script.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

MARKER = ".sfo_test_data"

# relative path -> size in bytes
FILES = {
    "photo-1.jpg": 1500,
    "photo-2.JPG": 800,
    "holiday.jfif": 2200,
    "scan.tiff": 4000,
    "logo.png": 600,
    "invoice March.pdf": 3000,
    "Invoice_april.PDF": 1200,
    "old report 2019.pdf": 2000,
    "report final.docx": 5000,
    "notes.txt": 120,
    "README": 40,
    "data.csv": 900,
    "song.mp3": 6000,
    "clip.mp4": 9000,
    "backup.tar.gz": 2500,
    "setup.exe": 7000,
    "weird.xyz": 64,
    "hidden-note.txt": 10,
    "sub1/photo-1.jpg": 1700,
    "sub1/invoice old.pdf": 400,
    "sub2/photo-1.jpg": 1900,
    "sub2/deep/readme.md": 200,
    "node_modules/pkg/index.js": 30,
    ".git/config": 30,
}


def content(name: str, size: int) -> bytes:
    seed = name.encode("utf-8") or b"x"
    return (seed * (size // len(seed) + 1))[:size]


def hide(path: Path) -> None:
    """Give a file the Windows 'hidden' attribute (does nothing on other systems)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x2)  # type: ignore[attr-defined]
    except Exception:
        pass


def create(target: Path) -> Path:
    downloads = target / "Downloads"
    for relative, size in FILES.items():
        path = downloads / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content(relative, size))
    old = datetime(2019, 6, 15, 12, 0).timestamp()
    os.utime(downloads / "old report 2019.pdf", (old, old))
    hide(downloads / "hidden-note.txt")
    (target / MARKER).write_text("Created by tools/make_test_data.py\n", encoding="utf-8")
    return downloads


def main(argv: list[str]) -> int:
    reset = "--reset" in argv
    args = [arg for arg in argv if not arg.startswith("--")]
    target = Path(args[0]) if args else Path.home() / "Desktop" / "SFO_TestData"

    if target.exists():
        if not reset:
            print(f"{target} already exists. Use --reset to recreate it, or choose another folder.")
            return 1
        if not (target / MARKER).exists():
            print(f"Refusing to delete {target}: it was not created by this script.")
            return 1
        shutil.rmtree(target)

    downloads = create(target)
    print(f"Created test data in {target}")
    print(f"Scan this folder in the app:   {downloads}")
    print(f"The default destination will be: {downloads}_Organized")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))