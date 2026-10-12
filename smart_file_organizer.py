from __future__ import annotations

import csv
import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "Smart File Organizer"
LOG_NAME = "organizer_history.csv"
DEFAULT_RULES = {
    "extension_folders": {
        ".pdf": "PDF",
        ".doc": "Documents",
        ".docx": "Documents",
        ".txt": "Text Files",
        ".rtf": "Documents",
        ".jpg": "Images",
        ".jpeg": "Images",
        ".png": "Images",
        ".gif": "Images",
        ".webp": "Images",
        ".bmp": "Images",
        ".mp3": "Audio",
        ".wav": "Audio",
        ".m4a": "Audio",
        ".flac": "Audio",
        ".aac": "Audio",
        ".mp4": "Videos",
        ".mov": "Videos",
        ".avi": "Videos",
        ".mkv": "Videos",
        ".cdr": "CorelDRAW",
        ".svg": "Vector Files",
        ".ai": "Vector Files",
        ".eps": "Vector Files",
        ".psd": "Design Files",
        ".xlsx": "Spreadsheets",
        ".xls": "Spreadsheets",
        ".csv": "Spreadsheets",
        ".ppt": "Presentations",
        ".pptx": "Presentations",
        ".zip": "Archives",
        ".rar": "Archives",
        ".7z": "Archives",
    }
}


def safe_destination(folder: Path, filename: str) -> Path:
    """Avoid overwriting an existing file by adding a numbered suffix."""
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    src = Path(filename)
    stem, suffix = src.stem, src.suffix
    index = 1
    while True:
        candidate = folder / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


class OrganizerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("820x700")
        self.root.minsize(740, 620)

        self.source_var = tk.StringVar()
        self.destination_var = tk.StringVar()
        self.keyword_var = tk.StringVar()
        self.keyword_folder_var = tk.StringVar(value="Keyword Matches")
        self.dry_run_var = tk.BooleanVar(value=True)
        self.include_subfolders_var = tk.BooleanVar(value=False)
        self.action_var = tk.StringVar(value="Move")
        self.status_var = tk.StringVar(value="Choose a source folder to begin.")
        self.last_actions: list[dict] = []
        self.busy = False

        self._build_ui()

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Smart File Organizer", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Sort files by extension and collect files whose names contain a keyword.",
            wraplength=760,
        ).pack(anchor="w", pady=(3, 14))

        paths = ttk.LabelFrame(outer, text="Folders", padding=10)
        paths.pack(fill="x", pady=(0, 10))
        self._path_row(paths, "Source folder", self.source_var, self.choose_source)
        self._path_row(paths, "Destination folder", self.destination_var, self.choose_destination)

        rules = ttk.LabelFrame(outer, text="Organization rules", padding=10)
        rules.pack(fill="x", pady=(0, 10))
        ttk.Label(rules, text="Filename keyword (optional):").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(rules, textvariable=self.keyword_var, width=30).grid(row=0, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(rules, text="Matching files folder:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(rules, textvariable=self.keyword_folder_var, width=30).grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(
            rules,
            text="Example: keyword 'Burna Boy' sends matching filenames to the keyword folder before extension sorting.",
            wraplength=700,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        rules.columnconfigure(1, weight=1)

        options = ttk.LabelFrame(outer, text="Safety options", padding=10)
        options.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(
            options,
            text="Preview only (dry run) — do not change any files",
            variable=self.dry_run_var,
        ).pack(anchor="w", pady=2)
        ttk.Checkbutton(
            options,
            text="Include files in subfolders (source files stay in place during preview)",
            variable=self.include_subfolders_var,
        ).pack(anchor="w", pady=2)
        ttk.Label(options, text="Action when preview is unchecked:").pack(anchor="w", pady=(8, 2))
        action_row = ttk.Frame(options)
        action_row.pack(anchor="w")
        ttk.Radiobutton(action_row, text="Move files", variable=self.action_var, value="Move").pack(side="left", padx=(0, 16))
        ttk.Radiobutton(action_row, text="Copy files", variable=self.action_var, value="Copy").pack(side="left")

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(0, 10))
        self.preview_btn = ttk.Button(buttons, text="Scan / Preview", command=self.run_organizer)
        self.preview_btn.pack(side="left")
        ttk.Button(buttons, text="Undo last run", command=self.undo_last_run).pack(side="left", padx=8)
        ttk.Button(buttons, text="Open destination", command=self.open_destination).pack(side="left")

        ttk.Label(outer, text="Activity log").pack(anchor="w")
        self.log = tk.Text(outer, height=13, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(4, 8))
        ttk.Label(outer, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x")

    def _path_row(self, parent, label, variable, command):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=17).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="Browse…", command=command).pack(side="left")

    def choose_source(self):
        path = filedialog.askdirectory(title="Choose source folder")
        if path:
            self.source_var.set(path)
            if not self.destination_var.get():
                self.destination_var.set(str(Path(path).parent / f"{Path(path).name}_Organized"))

    def choose_destination(self):
        path = filedialog.askdirectory(title="Choose destination folder")
        if path:
            self.destination_var.set(path)

    def write_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def classify(self, path: Path, keyword: str, keyword_folder: str) -> str:
        if keyword and keyword.casefold() in path.name.casefold():
            folder = keyword_folder.strip() or "Keyword Matches"
            return folder
        return DEFAULT_RULES["extension_folders"].get(path.suffix.casefold(), "Other Files")

    def run_organizer(self):
        if self.busy:
            return
        source_text = self.source_var.get().strip()
        destination_text = self.destination_var.get().strip()
        if not source_text or not destination_text:
            messagebox.showwarning(APP_NAME, "Choose both a source folder and a destination folder.")
            return
        source = Path(source_text).expanduser()
        destination = Path(destination_text).expanduser()
        if not source.is_dir():
            messagebox.showerror(APP_NAME, "The source folder does not exist or is not a folder.")
            return
        if source == destination or source in destination.parents:
            messagebox.showerror(
                APP_NAME,
                "Choose a destination outside the source folder. This avoids scanning files created by the organizer.",
            )
            return
        if destination in source.parents:
            messagebox.showerror(
                APP_NAME,
                "For safety, choose a destination that is not a parent of the source folder.",
            )
            return

        dry_run = self.dry_run_var.get()
        if not dry_run:
            action = self.action_var.get().lower()
            warning = (
                f"This will {action} files from:\n{source}\n\ninto:\n{destination}\n\n"
                "Use a test folder first. Continue?"
            )
            if not messagebox.askyesno(APP_NAME, warning, icon="warning"):
                return

        self.busy = True
        self.preview_btn.configure(state="disabled")
        self.status_var.set("Scanning files…")
        threading.Thread(target=self._organize_worker, args=(source, destination, dry_run), daemon=True).start()

    def _organize_worker(self, source: Path, destination: Path, dry_run: bool):
        keyword = self.keyword_var.get().strip()
        keyword_folder = self.keyword_folder_var.get().strip() or "Keyword Matches"
        recursive = self.include_subfolders_var.get()
        action = self.action_var.get().lower()
        try:
            iterator = source.rglob("*") if recursive else source.iterdir()
            files = []
            for item in iterator:
                if not item.is_file():
                    continue
                try:
                    item.resolve().relative_to(destination.resolve())
                    continue
                except (ValueError, OSError):
                    pass
                files.append(item)

            plans = []
            for item in files:
                folder_name = self.classify(item, keyword, keyword_folder)
                target_folder = destination / folder_name
                target = safe_destination(target_folder, item.name)
                plans.append((item, target))

            if not dry_run:
                destination.mkdir(parents=True, exist_ok=True)

            actions = []
            for item, target in plans:
                if dry_run:
                    self._ui(self.write_log, f"[PREVIEW] {item}  ->  {target}")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target = safe_destination(target.parent, target.name)
                if action == "copy":
                    shutil.copy2(item, target)
                    action_type = "copy"
                else:
                    shutil.move(str(item), str(target))
                    action_type = "move"
                actions.append({"action": action_type, "source": str(item), "target": str(target)})
                self._append_history(action_type, item, target)
                self._ui(self.write_log, f"[{action_type.upper()}] {item}  ->  {target}")

            if not plans:
                self._ui(self.write_log, "No files found in the selected source folder.")
            summary = f"Scanned {len(files)} file(s); {len(plans)} match(es)."
            if dry_run:
                summary += " Preview only: no files were changed."
            else:
                summary += f" Completed {len(actions)} {action}(s)."
            self.last_actions = actions
            self._ui(self.write_log, summary)
            self._ui(self.status_var.set, summary)
        except Exception as exc:
            self._ui(messagebox.showerror, APP_NAME, f"An error occurred:\n{exc}")
            self._ui(self.status_var.set, "Run failed. Check the activity log.")
        finally:
            self._ui(self.preview_btn.configure, state="normal")
            self.busy = False

    def _append_history(self, action, source, target):
        destination = Path(self.destination_var.get())
        destination.mkdir(parents=True, exist_ok=True)
        log_path = destination / LOG_NAME
        new_file = not log_path.exists()
        with log_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if new_file:
                writer.writerow(["timestamp", "action", "source", "target"])
            writer.writerow([datetime.now().isoformat(timespec="seconds"), action, str(source), str(target)])

    def _ui(self, callback, *args, **kwargs):
        self.root.after(0, lambda: callback(*args, **kwargs))

    def undo_last_run(self):
        if not self.last_actions:
            messagebox.showinfo(APP_NAME, "There are no file operations from this session to undo.")
            return
        if not messagebox.askyesno(APP_NAME, "Undo the last completed run? Files may be moved back or copied files removed."):
            return
        errors = []
        for entry in reversed(self.last_actions):
            source = Path(entry["source"])
            target = Path(entry["target"])
            try:
                if not target.exists():
                    continue
                if entry["action"] == "move":
                    source.parent.mkdir(parents=True, exist_ok=True)
                    restored = safe_destination(source.parent, source.name)
                    shutil.move(str(target), str(restored))
                    self.write_log(f"[UNDO MOVE] {target}  ->  {restored}")
                else:
                    target.unlink()
                    self.write_log(f"[UNDO COPY] Removed {target}")
            except Exception as exc:
                errors.append(f"{target}: {exc}")
        self.last_actions = []
        if errors:
            messagebox.showwarning(APP_NAME, "Some operations could not be undone:\n" + "\n".join(errors[:8]))
        else:
            messagebox.showinfo(APP_NAME, "Undo completed for the recorded operations.")

    def open_destination(self):
        path = Path(self.destination_var.get().strip()).expanduser()
        if not path.is_dir():
            messagebox.showinfo(APP_NAME, "The destination folder does not exist yet.")
            return
        import os
        os.startfile(str(path))


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except tk.TclError:
        pass
    OrganizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
