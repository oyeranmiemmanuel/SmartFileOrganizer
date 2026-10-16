# -*- mode: python ; coding: utf-8 -*-
# One-file build: dist\SmartFileOrganizer.exe (windowed, no console).
# Build with:  build_exe.bat   (or: python -m PyInstaller --noconfirm --clean SmartFileOrganizer.spec)
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
ICON = ROOT / "assets" / "icon.ico"

# CustomTkinter ships themes and fonts as data files that must be bundled.
datas = collect_data_files("customtkinter")
if ICON.exists():
    datas.append((str(ICON), "assets"))

# legacy_app is imported inside a function (the --legacy fallback), so name it explicitly.
hiddenimports = collect_submodules("organizer") + ["legacy_app"]

a = Analysis(
    [str(ROOT / "smart_file_organizer.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SmartFileOrganizer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed programs trigger more antivirus false alarms
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,
)

hiddenimports = (
    collect_submodules("organizer")
    + ["legacy_app", "organizer.ui.preview_page"]
)