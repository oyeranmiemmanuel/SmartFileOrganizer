# Building SmartFileOrganizer.exe

Build on Windows, for Windows. These steps have been written but **not yet
run**: do the checks in `TESTING_CHECKLIST.md` before you rely on or share a
build.

## What you get

| Build | Command | Output | Use it for |
|---|---|---|---|
| Single file | `build_exe.bat` | `dist\SmartFileOrganizer.exe` | Sharing one file |
| Folder (with console) | `build_folder.bat` | `dist\SmartFileOrganizer_folder\SmartFileOrganizer.exe` | Finding out why something fails |

The single-file build unpacks itself into a temporary folder on every start, so
it opens more slowly (a few seconds on an older laptop) than the folder build.

## One-time setup

```bat
cd /d "C:\path\to\SmartFileOrganizer"
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-build.txt
```

Use the same Python you use to run the app (3.10 or newer, 64-bit, with Tk).

## Build

Easiest: double-click or run the scripts. They install the build tools, create
`assets\icon.ico` if missing, run the tests, then build. Add `skip-tests` to
skip the test run.

```bat
build_folder.bat
build_exe.bat
```

Manual equivalent:

```bat
python tools\make_icon.py
python -m pytest -q
python -m PyInstaller --noconfirm --clean SmartFileOrganizer.spec
```

## How the build is put together

- `SmartFileOrganizer.spec` starts from `smart_file_organizer.py` and bundles all
  of the `organizer` package plus `legacy_app.py`.
- CustomTkinter's themes and fonts are data files, so the spec bundles them with
  `collect_data_files("customtkinter")`.
- `assets\icon.ico` is bundled and also used as the exe icon.
- UPX compression is off, because packed programs trigger more antivirus alarms.
- The one-file build is windowed (no console). The folder build keeps a console.

## Where the app keeps its data

Never next to the exe and never in the temporary unpack folder (that folder is
deleted when the app closes). Everything is under
`%LOCALAPPDATA%\SmartFileOrganizer\`:

| Item | Location |
|---|---|
| Settings | `settings.json` |
| Your rules | `rules.json` (a backup is `rules.json.bak`) |
| Run history | `history\` |
| Logs | `logs\smartfileorganizer.log`, `logs\launcher.log` |

Deleting that folder resets the app; it does not touch your organized files.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `'python' is not recognized` | Install Python from python.org with "Add to PATH", or use `py` instead. |
| `No module named PyInstaller` | Run `python -m pip install -r requirements-build.txt` in the active `.venv`. |
| `No module named tkinter` | Reinstall Python and tick "tcl/tk and IDLE". |
| The exe starts and immediately closes | Run the **folder build** from a Command Prompt to read the message. Also read `%LOCALAPPDATA%\SmartFileOrganizer\logs\`. |
| Window opens but looks plain or errors mention a theme/json file | CustomTkinter data was not bundled. Check the spec still contains `collect_data_files("customtkinter")`, then rebuild with `--clean`. |
| `ModuleNotFoundError` for an `organizer...` module in the exe | Rebuild with `--clean`. The spec uses `collect_submodules("organizer")`; add any missing name to `hiddenimports`. |
| Classic interface opens instead of the new one | CustomTkinter was not available in the build environment. Reinstall requirements and rebuild. |
| `PermissionError` writing `dist\SmartFileOrganizer.exe` | The exe is still running, or antivirus/OneDrive is locking it. Close it, or build in a folder outside OneDrive. |
| Antivirus quarantines the exe, or Windows SmartScreen warns | Common for unsigned programs built with PyInstaller, especially one-file builds. Use the folder build, add an exclusion for `dist`, or sign the exe with a code-signing certificate. |
| Build fails on a very new Python version | Run `python -m pip install --upgrade pyinstaller` and retry, or use a slightly older Python. |
| Icon missing | Run `python tools\make_icon.py`, then rebuild with `--clean`. |
| Old behaviour after changing code | Always build with `--clean` (the scripts do). |

## Sharing

Send the single `SmartFileOrganizer.exe`. It needs no Python on the other PC.
Tell people the data folder above and that a first start can take a few seconds.