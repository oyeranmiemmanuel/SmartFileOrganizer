# Testing checklist (source version and packaged exe)

Run the checks twice: once with `python smart_file_organizer.py` and once with
the built `dist\SmartFileOrganizer.exe`. Tick each box only after you have seen
the expected result. **Use disposable test data, never your real files.**

## Test data

```bat
python tools\make_test_data.py
```

This creates `Desktop\SFO_TestData\Downloads` (the folder you scan). Counts below
come from that data; if `hidden-note.txt` is not hidden on your system they are
one higher.

| Scan | Files | File types |
|---|---|---|
| Without subfolders | 17 | 14 |
| With subfolders | 21 | 14 |

`node_modules` and `.git` are never scanned. Reset the data between runs:
`python tools\make_test_data.py --reset` (and delete `SFO_TestData\Downloads_Organized`).

Record results here: Source [ ]  Packaged exe [ ]  Date: ________

## A. Startup (packaged exe only for A3-A5)

| # | Step | Expected | Source | Exe |
|---|---|---|---|---|
| A1 | Start the app | Window opens with sidebar and Dashboard, no error dialog | [ ] | [ ] |
| A2 | Close and reopen | Last source folder and options are remembered | [ ] | [ ] |
| A3 | Run the exe on a PC without Python (or note "not tested") | It starts | | [ ] |
| A4 | Check `%LOCALAPPDATA%\SmartFileOrganizer\` | `settings.json` and `logs\` exist | [ ] | [ ] |
| A5 | Move the exe to another folder and start it | Works; data stays in the same `%LOCALAPPDATA%` folder | | [ ] |
| A6 | Window icon | Custom icon shows in title bar and taskbar | [ ] | [ ] |

## B. Scanning and classification

| # | Step | Expected | Source | Exe |
|---|---|---|---|---|
| B1 | Choose `...\SFO_TestData\Downloads`, press Scan folder | Progress shown, then Scan Results opens: 17 files, 14 types | [ ] | [ ] |
| B2 | Look at `.jfif` | Category Images; `.tar.gz` is one type, Archives; "(no extension)" row exists | [ ] | [ ] |
| B3 | Unknown type `.xyz` | Category Other Files | [ ] | [ ] |
| B4 | Turn on Include subfolders, rescan | 21 files; `node_modules` and `.git` are listed under Skipped & errors | [ ] | [ ] |
| B5 | Sort a column; type `pdf` in the filter | Sorting works; only matching rows show | [ ] | [ ] |
| B6 | Scan, press Cancel immediately on a large folder | Status shows cancelled/partial; no crash | [ ] | [ ] |

## C. Choosing file types

| # | Step | Expected | Source | Exe |
|---|---|---|---|---|
| C1 | Select none; filter `.jfif`; press Only visible | Only `.jfif` is ticked; label says 1 of 14 types, 1 file | [ ] | [ ] |
| C2 | Click a checkbox, and press Space on a row | Tick toggles; scroll position and selection stay | [ ] | [ ] |
| C3 | Continue to Preview | Only the ticked types are listed | [ ] | [ ] |

## D. Find Files

| # | Step | Expected | Source | Exe |
|---|---|---|---|---|
| D1 | Name `invoice`, Contains, Search | 2 matches (3 with subfolders), all ticked | [ ] | [ ] |
| D2 | Name `*.pdf`, Wildcard | All PDFs, including `.PDF` | [ ] | [ ] |
| D3 | File types `jpg, jfif` | Only those types | [ ] | [ ] |
| D4 | Size to `1` KB | Only files of 1 KB or less | [ ] | [ ] |
| D5 | Modified to `2019-12-31` | Only `old report 2019.pdf` | [ ] | [ ] |
| D6 | Category `PDF`; combine with name `invoice` | Criteria combine (AND) | [ ] | [ ] |
| D7 | Enter `abc` as a size | Red message, no search | [ ] | [ ] |
| D8 | Untick one match, press Preview ticked files | Preview lists only the ticked files; Scan Results shows "individual files from Find Files" | [ ] | [ ] |
| D9 | Run it (Move) | Only those files move; other files of the same type stay | [ ] | [ ] |

## E. Preview and conflicts (reset data first)

| # | Step | Expected | Source | Exe |
|---|---|---|---|---|
| E1 | Scan with subfolders, all types, Preview (Move, Rename) | `photo-1.jpg` ×3: two show Renamed (`photo-1 (1).jpg`, `photo-1 (2).jpg`) | [ ] | [ ] |
| E2 | Switch conflicts to Skip | Those two show Skipped with a reason | [ ] | [ ] |
| E3 | Layout: Keep subfolder structure | No conflicts; paths include `sub1`, `sub2` | [ ] | [ ] |
| E4 | Filters: status Conflicts, category, type, search | Table narrows correctly | [ ] | [ ] |
| E5 | Create a file in the destination, then press Run | Preview is refreshed and **nothing** moves | [ ] | [ ] |
| E6 | Destination inside the source | Clear error; scan/preview refuse | [ ] | [ ] |

## F. Move, Copy, history, undo (reset data first)

| # | Step | Expected | Source | Exe |
|---|---|---|---|---|
| F1 | Preview Move for all, press Run, confirm | Progress bar; report; files are in category folders; originals gone | [ ] | [ ] |
| F2 | Run page lists skipped/failed files with reasons | Reasons are readable | [ ] | [ ] |
| F3 | Save report and Export CSV | Files are created and open | [ ] | [ ] |
| F4 | History | The run is listed with counts; Details shows each file | [ ] | [ ] |
| F5 | Close and reopen the app | History is still there | [ ] | [ ] |
| F6 | Undo the run | Summary first, then files return to the original folders; nothing overwritten | [ ] | [ ] |
| F7 | Run a Move, edit one moved file, then Undo | That file is left alone and the reason is shown | [ ] | [ ] |
| F8 | Run a Copy | Originals remain; copies exist | [ ] | [ ] |
| F9 | Undo the Copy | Copies are removed; originals untouched | [ ] | [ ] |
| F10 | Run a larger Move and press Cancel | Stops after the current file; report shows "Not run" files | [ ] | [ ] |
| F11 | Try closing the window mid-run | App refuses and asks you to cancel first | [ ] | [ ] |

## G. Rules

| # | Step | Expected | Source | Exe |
|---|---|---|---|---|
| G1 | Scan Results: double-click `.jfif`, destination `Photos` | Row shows `Photos`; `rules.json` exists | [ ] | [ ] |
| G2 | Rules page: rename Images to Pictures | Preview uses `Pictures` | [ ] | [ ] |
| G3 | Add keyword rule `invoice` -> `Invoices` | Invoice files go to `Invoices` in the preview | [ ] | [ ] |
| G4 | Break `rules.json` (delete a brace), Reload | Red error; edit buttons locked; built-in rules used | [ ] | [ ] |
| G5 | Reset all my changes | `rules.json.bak` created; defaults restored | [ ] | [ ] |
| G6 | Try a bad folder name like `a:b` | Dialog explains the allowed name | [ ] | [ ] |

## H. Appearance and settings

| # | Step | Expected | Source | Exe |
|---|---|---|---|---|
| H1 | Settings: Light, Dark, System | Whole UI and tables change | [ ] | [ ] |
| H2 | Change interface size, restart | New size applied after restart | [ ] | [ ] |
| H3 | Resize the window small | No overlapping controls; pages stay usable | [ ] | [ ] |

## I. Robustness

| # | Step | Expected | Source | Exe |
|---|---|---|---|---|
| I1 | Delete the source folder after scanning, then Run | Files reported as failed/skipped; no crash | [ ] | [ ] |
| I2 | Open a scanned file in another program, then Move | That file fails or is skipped with a reason; the rest continue | [ ] | [ ] |
| I3 | `python smart_file_organizer.py --legacy` | The classic interface opens | [ ] | [ ] |
| I4 | Look at `logs\smartfileorganizer.log` after the tests | No unexplained errors | [ ] | [ ] |

## Reporting a problem

Note the step number, what you saw, and attach the newest lines of
`%LOCALAPPDATA%\SmartFileOrganizer\logs\smartfileorganizer.log`. For packaged
builds also try the folder build from `build_folder.bat` and copy the console
text.