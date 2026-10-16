# -*- mode: python ; coding: utf-8 -*-
# Folder build for troubleshooting: dist\SmartFileOrganizer_folder\SmartFileOrganizer.exe
# It shows a console window, so any error message stays visible.
# Build with:  build_folder.bat   (or: python -m PyInstaller --noconfirm --clean SmartFileOrganizer_folder.spec)
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
ICON = ROOT / "assets" / "icon.ico"

datas = collect_data_files("customtkinter")
if ICON.exists():
    datas.append((str(ICON), "assets"))

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
    [],
    exclude_binaries=True,
    name="SmartFileOrganizer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.exists() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SmartFileOrganizer_folder",
)