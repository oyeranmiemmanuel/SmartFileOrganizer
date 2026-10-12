# Smart File Organizer (Windows MVP)

A Python desktop utility that previews and organizes files by extension or filename keyword.

## Requirements
- Windows 10/11
- Python 3.10+ with Tkinter (the standard Windows Python installer usually includes it)
- No AI, API key, or third-party Python packages required

## Run
Open Command Prompt in this folder and run:

```bat
python --version
python smart_file_organizer.py
```

If `python` is not recognized, try `py smart_file_organizer.py`.

## Safe first test
1. Create a disposable test folder and put copies of a few files in it.
2. Open the app and choose that test folder as Source.
3. Leave the destination as the suggested `Organized` folder beside the source.
4. Enter an optional keyword, such as `Burna Boy`, to route filenames containing it into a separate folder.
5. Click **Scan / Preview** and inspect the proposed destinations.
6. Only after checking the preview, uncheck **Preview only** and select Move or Copy.
7. Confirm the warning dialog.

The default behavior is preview-only. Unknown extensions go to `Other Files`. Matching keyword files are routed to the keyword folder before extension classification.

## Current MVP limitations
- Keyword matching uses the filename only; it does not yet inspect MP3 ID3 artist tags.
- The app currently supports common file extensions and can be expanded.
- Preview plans are shown in the activity log. Undo is limited to operations performed in the current running session.
- Test with copies of files before organizing important data. This is not a data recovery utility.
