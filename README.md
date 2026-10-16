# Smart File Organizer

A Windows desktop app that scans a folder, shows exactly what it would do, and then moves or copies files into category folders. Nothing is changed until you review a preview and confirm, and every run can be undone.

## Features

- **Scan** a folder (optionally with subfolders) and see every file type found, with counts, sizes, categories and destination folders.
- **Choose what to organize**: tick whole file types, or use **Find Files** to search for individual files (by name, type, category, size, date or subfolder), tick the matches, and organize only those.
- **Customize**: send a file type to any folder, rename category folders, and add filename keyword rules. Changes are saved to a small JSON file.
- **Preview** the complete plan with filters, Move or Copy, and conflict handling (rename or skip). Existing files are never overwritten.
- **Run** with live progress, safe cancel, and a report of anything skipped or failed.
- **History and undo** that survive restarts. Undo first checks that files have not changed.
- Light and dark appearance, and a classic fallback interface.

## Safety model

- Scanning and previewing never change any file.
- Before running, the plan is rebuilt; if the destination changed since the preview, nothing runs and you get the new preview.
- Each file is re-checked just before it is touched.
- Names are never overwritten: conflicts are renamed (`name (1).ext`) or skipped.
- Undo only touches files that still match what the app recorded.

Still, **try it on copies of your files first**.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer (64-bit) with Tk (included in the standard python.org installer)

## Install and run from source

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python smart_file_organizer.py
```

`Run Smart File Organizer.bat` does the same and uses `.venv` when present. The previous interface is still available with `python smart_file_organizer.py --legacy`, and opens automatically if CustomTkinter is missing.

## Using the app

1. **Dashboard**: choose the source folder. The destination defaults to `<source>_Organized` beside it. Press **Scan folder**.
2. **Scan Results**: tick the file types to include. Double-click a row to choose where that type goes.
3. Or open **Find Files**, enter criteria, press **Search**, untick any matches you do not want, and press **Preview ticked files**.
4. **Preview**: choose Move or Copy and how conflicts are handled; review the table; press **Run**.
5. **Run & Report** shows progress and the final report. **History** lists every run and lets you undo it.

### Find Files criteria (all optional, combined with AND)

| Field | Meaning |
|---|---|
| File name | Contains, starts with, ends with, or wildcard (`*` and `?`). Capitals do not matter. |
| File types | For example `jpg, png`. Use `none` for files without an extension. |
| Category | The category the current rules give the file. |
| Size from/to | With a KB, MB or GB unit. |
| Modified from/to | Dates as `2024-03-31`. The end date is included. |
| In subfolder containing | Part of a subfolder name (for scans that include subfolders). |

## Changing classifications

Use the **Rules** page, or double-click a file type on Scan Results. You can also edit the file directly: Settings -> **Open rules file**. It only lists your changes:

```json
{
  "version": 1,
  "folder_names": {"Images": "Pictures"},
  "extension_overrides": {".xyz": "Images"},
  "keyword_rules": [{"keyword": "invoice", "folder": "Invoices"}]
}
```

A damaged rules file is reported on screen and the built-in rules are used; the app will not overwrite it until you fix or reset it.

## Where data is stored

`%LOCALAPPDATA%\SmartFileOrganizer\`

| Item | Location |
|---|---|
| Settings | `settings.json` |
| Your rules | `rules.json` (backup: `rules.json.bak`) |
| Run history | `history\` |
| Logs | `logs\` |

Deleting this folder resets the app. It never touches your organized files. The packaged exe uses the same folder.

## Tests

```bat
python -m pip install -r requirements-dev.txt
python -m pytest
```

Manual checks for the app and the exe are in `docs/TESTING_CHECKLIST.md`. Disposable test files: `python tools\make_test_data.py`.

## Building the single-file exe

```bat
build_folder.bat   rem folder build with a console, for troubleshooting
build_exe.bat      rem dist\SmartFileOrganizer.exe
```

Details, troubleshooting and antivirus notes: `docs/PACKAGING.md`. A build is only trustworthy after you have run the checklist on it.

## Project layout

```text
smart_file_organizer.py      launcher (new interface; --legacy for the old one)
legacy_app.py                the original interface
organizer/                   engine and interface
  categories.py scanner.py search.py selection.py planner.py
  fileops.py executor.py history.py undo.py jobs.py reports.py
  rules_editor.py settings.py workers.py resources.py app.py
  ui/                        CustomTkinter pages and widgets
tests/                       automated tests
tools/                       icon and test-data generators
docs/                        packaging guide and manual checklist
```

## Known limitations

- Windows-first. Other systems are not supported.
- File types are judged by extension only; contents are never inspected.
- Undo relies on size and modified time to detect changes.
- Very large previews (tens of thousands of files) filter slowly.
- The one-file exe is unsigned, so antivirus or SmartScreen may warn about it.

## License

MIT. See `LICENSE`.