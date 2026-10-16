"""The CustomTkinter application window: sidebar, pages, background tasks and settings.

All file-system work comes from the engine modules (scanner, planner, executor,
history, undo) through ``jobs``. The window only displays state and starts
background tasks. A task reports back through a queue that is polled on the
main thread; widgets are never touched from another thread. Only one task
runs at a time (``busy``).
"""

from __future__ import annotations

import copy
import logging
import os
import subprocess
import tkinter as tk
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Callable, Iterable

import customtkinter as ctk

from . import __version__, jobs, rules_editor
from .categories import (
    NO_EXTENSION_CATEGORY,
    ClassificationRules,
    RulesError,
    default_rules,
    parse_rules,
)
from .executor import ExecutionProgress, ExecutionResult
from .history import HistoryError, HistoryStore, RunSummary, default_history_dir, export_run_csv
from .paths import default_destination, sanitize_name
from .planner import Plan, PlanValidationError, validate_paths
from .reports import (
    confirmation_text,
    preflight_summary,
    report_text,
    run_details_text,
    undo_confirmation_text,
    undo_report_text,
)
from .resources import app_icon_path
from .scanner import ScanProgress, ScanResult, scan_directory
from .search import SearchCriteria, SearchHit, find_files
from .selection import Selection, SelectionSummary, all_extensions, summarize_selection
from .settings import (
    APPEARANCE_MODES,
    Settings,
    SettingsStore,
    default_log_dir,
    default_rules_path,
)
from .undo import UndoProgress, UndoResult, undo_run
from .ui.dashboard import DashboardPage
from .ui.dialogs import FormField, ask_form
from .ui.find_page import FindPage
from .ui.history_page import HistoryPage
from .ui.operation_state import (
    DEFAULT_ACTION,
    DEFAULT_CONFLICT,
    DEFAULT_LAYOUT,
    PlanStatus,
    RunStatus,
    plan_options,
    run_badge,
)
from .ui.preview_page import PreviewPage
from .ui.rules_page import RulesPage
from .ui.run_page import RunPage
from .ui.scan_page import ScanPage
from .ui.settings_page import SettingsPage
from .ui.state import ScanStatus, status_badge
from .ui.theme import (
    ACCENT,
    ACCENT_HOVER,
    APP_NAME,
    MUTED,
    NAV_HOVER,
    ON_ACCENT,
    SIDEBAR_BG,
    TEXT,
    apply_treeview_style,
    font,
    labeled,
)
from .ui.widgets import Page, StatusBadge, TextDialog
from .workers import ERROR, PROGRESS, RESULT, BackgroundTask

logger = logging.getLogger(__name__)

NAV = (
    ("dashboard", "dashboard", "Dashboard"),
    ("scan", "scan", "Scan Results"),
    ("find", "find", "Find Files"),
    ("preview", "preview", "Preview"),
    ("run", "run", "Run & Report"),
    ("history", "history", "History"),
    ("rules", "rules", "Rules"),
    ("settings", "settings", "Settings"),
)


class App(ctk.CTk):
    def __init__(self, store: SettingsStore, settings: Settings, log_path: Path | None) -> None:
        super().__init__()
        self.store = store
        self.settings = settings
        self.log_path = log_path
        self.ui_scale = settings.ui_scale / 100

        self.title(APP_NAME)
        self.geometry("1180x720")
        self.minsize(960, 580)
        self.report_callback_exception = self._report_callback_exception  # type: ignore[method-assign]
        apply_treeview_style(self.ui_scale)
        icon = app_icon_path()
        if icon is not None:  # customtkinter sets its own icon late, so set ours after it
            self.after(250, lambda: self._set_icon(icon))

        # Rules
        self.rules: ClassificationRules = default_rules()
        self.rules_overlay: dict[str, Any] = rules_editor.new_overlay()
        self.rules_warnings: list[str] = []
        self.rules_origin = "built-in default rules"
        self.rules_error = ""
        self._load_rules()

        # Scan and selection state
        self.scan: ScanResult | None = None
        self.scan_status = ScanStatus.IDLE
        self.scan_progress: ScanProgress | None = None
        self.scan_error = ""
        self.scan_note = ""
        self.selected_extensions: set[str] = set()
        self.selection_mode = "types"  # "types" (whole file types) or "files" (chosen on Find Files)
        self.selected_files: set[str] = set()
        self.selection_version = 0

        # Find Files state
        self.search_results: list[SearchHit] | None = None
        self.found_ticked: set[str] = set()
        self.found_version = 0

        # Preview state
        self.plan: Plan | None = None
        self.plan_status = PlanStatus.NONE
        self.plan_error = ""
        self.plan_note = ""
        self._plan_version = 0
        self.action_label = DEFAULT_ACTION
        self.conflict_label = DEFAULT_CONFLICT
        self.layout_label = DEFAULT_LAYOUT

        # Run, history and undo state
        self.run_status = RunStatus.IDLE
        self.run_progress: ExecutionProgress | None = None
        self.run_result: ExecutionResult | None = None
        self.run_plan: Plan | None = None
        self.run_error = ""
        self.history = HistoryStore(default_history_dir())
        self.history_runs: list[RunSummary] = []
        self.history_error = ""
        self.undo_progress: UndoProgress | None = None
        self.undo_message = ""
        self.reload_history()

        # Background task
        self.cancelling = False
        self._task: BackgroundTask | None = None
        self._task_kind = ""
        self._handlers: tuple[Callable | None, Callable | None, Callable | None] = (None, None, None)
        self._poll_id: str | None = None
        self._refresh_id: str | None = None
        self._suppress = False
        self._dialog_open = False
        self._current_page = "dashboard"

        # Shared variables
        source = settings.source if settings.source and Path(settings.source).is_dir() else ""
        self.source_var = tk.StringVar(master=self, value=source)
        self.destination_var = tk.StringVar(master=self, value="")
        self.recursive_var = tk.BooleanVar(master=self, value=settings.recursive)
        self.hidden_var = tk.BooleanVar(master=self, value=settings.include_hidden)
        if settings.destination_custom and settings.destination:
            self.destination_var.set(settings.destination)
        else:
            self._set_destination_auto()
        self.source_var.trace_add("write", self._on_source_edited)
        self.destination_var.trace_add("write", self._on_destination_edited)

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_page("dashboard")
        self.after(60, self._fit_to_screen)

    def _set_icon(self, icon: Path) -> None:
        try:
            self.iconbitmap(str(icon))
        except tk.TclError:
            pass

    # ----------------------------------------------------------- properties

    @property
    def busy(self) -> bool:
        return self._task is not None

    @property
    def task_kind(self) -> str:
        return self._task_kind

    @property
    def rules_editable(self) -> bool:
        return not self.rules_error

    @property
    def has_selection(self) -> bool:
        if self.selection_mode == "files":
            return bool(self.selected_files)
        return bool(self.selected_extensions)

    # ------------------------------------------------------------- layout

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color=SIDEBAR_BG)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        spacer_row = 2 + len(NAV)
        sidebar.grid_rowconfigure(spacer_row, weight=1)

        ctk.CTkLabel(sidebar, text="Smart File", font=font(22, "bold"), anchor="w").grid(
            row=0, column=0, sticky="ew", padx=20, pady=(22, 0)
        )
        ctk.CTkLabel(sidebar, text="Organizer", font=font(22, "bold"), text_color=ACCENT, anchor="w").grid(
            row=1, column=0, sticky="ew", padx=20, pady=(0, 14)
        )

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        for row, (key, icon, label) in enumerate(NAV, start=2):
            button = ctk.CTkButton(
                sidebar, text=labeled(icon, label), anchor="w", height=36, corner_radius=8,
                font=font(14), command=lambda k=key: self.show_page(k),
            )
            button.grid(row=row, column=0, sticky="ew", padx=12, pady=2)
            self._nav_buttons[key] = button

        self.sidebar_badge = StatusBadge(sidebar)
        self.sidebar_badge.grid(row=spacer_row + 1, column=0, padx=16, pady=(0, 8), sticky="w")
        ctk.CTkLabel(sidebar, text=f"Version {__version__}", text_color=MUTED, font=font(11), anchor="w").grid(
            row=spacer_row + 2, column=0, sticky="ew", padx=20, pady=(0, 14)
        )

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=0, column=1, sticky="nsew", padx=24, pady=18)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self.run_page = RunPage(content, self)
        self.history_page = HistoryPage(content, self)
        self.pages: dict[str, Page] = {
            "dashboard": DashboardPage(content, self),
            "scan": ScanPage(content, self),
            "find": FindPage(content, self),
            "preview": PreviewPage(content, self),
            "run": self.run_page,
            "history": self.history_page,
            "rules": RulesPage(content, self),
            "settings": SettingsPage(content, self),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()

    def show_page(self, name: str) -> None:
        for page in self.pages.values():
            page.grid_remove()
        self._current_page = name
        page = self.pages[name]
        page.grid(row=0, column=0, sticky="nsew")
        if name == "history":
            self.reload_history()
        page.refresh()
        self._update_nav()
        if name == "preview":
            self._maybe_build_preview()

    def _update_nav(self) -> None:
        for key, button in self._nav_buttons.items():
            if key == self._current_page:
                button.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT)
            else:
                button.configure(fg_color="transparent", hover_color=NAV_HOVER, text_color=TEXT)

    def refresh_all(self) -> None:
        self._refresh_id = None
        for page in self.pages.values():
            page.refresh()
        self.sidebar_badge.set(*self._sidebar_status())

    def _sidebar_status(self) -> tuple[str, str]:
        kind = self._task_kind
        if kind == "run":
            return run_badge(RunStatus.RUNNING, None, self.cancelling)
        if kind == "preview":
            return "Building preview…", "info"
        if kind == "search":
            return "Searching…", "info"
        if kind in ("undo", "undo_check"):
            return "Undoing…", "info"
        return status_badge(self.scan_status, self.cancelling)

    def _schedule_refresh(self) -> None:
        if self._refresh_id is not None:
            self.after_cancel(self._refresh_id)
        self._refresh_id = self.after(250, self.refresh_all)

    def _fit_to_screen(self) -> None:
        self.update_idletasks()
        too_wide = self.winfo_width() > self.winfo_screenwidth() - 20
        too_tall = self.winfo_height() > self.winfo_screenheight() - 80
        if too_wide or too_tall:
            try:
                self.state("zoomed")
            except tk.TclError:
                pass

    # -------------------------------------------------------- background tasks

    def _launch(
        self,
        kind: str,
        job: Callable[[Any, Any], Any],
        *,
        on_progress: Callable[[Any], None] | None = None,
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> bool:
        if self._task is not None:
            return False
        self.cancelling = False
        self._task = BackgroundTask(job, name=kind)
        self._task_kind = kind
        self._handlers = (on_progress, on_result, on_error)
        self._task.start()
        self._poll_id = self.after(100, self._poll_task)
        return True

    def _poll_task(self) -> None:
        self._poll_id = None
        task = self._task
        if task is None:
            return
        on_progress, on_result, on_error = self._handlers
        for event in task.poll():
            if event.kind == PROGRESS:
                if on_progress is not None:
                    on_progress(event.payload)
                continue
            self._task = None
            self._task_kind = ""
            self.cancelling = False
            if event.kind == RESULT:
                if on_result is not None:
                    on_result(event.payload)
            else:
                logger.error("A background task failed", exc_info=event.payload)
                if on_error is not None:
                    on_error(event.payload)
                else:
                    self.refresh_all()
        if self._task is task:
            self._poll_id = self.after(100, self._poll_task)

    def cancel_task(self) -> None:
        if self._task is not None and not self.cancelling:
            self.cancelling = True
            self._task.cancel()
            self.refresh_all()

    # -------------------------------------------------------------- rules

    def _load_rules(self) -> None:
        path = default_rules_path()
        try:
            overlay = rules_editor.load_overlay(path)
            loaded = parse_rules(overlay)
        except RulesError as exc:
            logger.warning("Rules file could not be used: %s", exc)
            self.rules, self.rules_warnings = default_rules(), []
            self.rules_overlay = rules_editor.new_overlay()
            self.rules_origin, self.rules_error = "built-in default rules", str(exc)
            return
        self.rules = loaded.rules
        self.rules_warnings = list(loaded.warnings)
        self.rules_overlay = overlay
        self.rules_origin = f"your rules file ({path})" if path.exists() else "built-in default rules"
        self.rules_error = ""

    def _on_rules_changed(self, note: str = "The rules changed, so the preview was cleared.") -> None:
        self.selection_version += 1
        self._clear_search_state()
        self._invalidate_plan(note)
        self.refresh_all()

    def reload_rules(self) -> None:
        self._load_rules()
        self._on_rules_changed("The rules were reloaded, so the preview was cleared.")
        if self.scan is not None:
            self.scan_note = "Rules reloaded. Scan again if you changed multi-part extensions such as .tar.gz."

    def open_rules_file(self) -> None:
        path = default_rules_path()
        if not path.exists():
            try:
                rules_editor.save_overlay(path, rules_editor.new_overlay())
            except OSError as exc:
                messagebox.showerror(APP_NAME, f"The rules file could not be created:\n{exc}", parent=self)
                return
        try:
            subprocess.Popen(["notepad.exe", str(path)])
        except OSError:
            messagebox.showinfo(APP_NAME, f"Open this file in a text editor:\n{path}", parent=self)

    def _edit_overlay(self, mutate: Callable[[dict[str, Any]], None]) -> bool:
        """Apply an edit to the rules file: validate first, save second, and never clobber a broken file."""
        if not self.rules_editable:
            messagebox.showwarning(
                APP_NAME,
                f"Your rules file has a problem, so it cannot be edited here:\n\n{self.rules_error}\n\n"
                "Fix it with Open rules file and press Reload, or use Reset all my changes.",
                parent=self,
            )
            return False
        candidate = copy.deepcopy(self.rules_overlay)
        path = default_rules_path()
        try:
            mutate(candidate)
            loaded = parse_rules(candidate)
            rules_editor.save_overlay(path, candidate)
        except (ValueError, OSError) as exc:  # RulesError is a ValueError
            messagebox.showerror(APP_NAME, f"The change could not be saved:\n{exc}", parent=self)
            return False
        self.rules_overlay = candidate
        self.rules = loaded.rules
        self.rules_warnings = list(loaded.warnings)
        self.rules_origin = f"your rules file ({path})"
        self.rules_error = ""
        self._on_rules_changed()
        return True

    @staticmethod
    def _folder_error(values: dict[str, str], key: str = "folder") -> str | None:
        text = values.get(key, "")
        if not text:
            return "Enter a folder name."
        cleaned = sanitize_name(text)
        if cleaned != text:
            return f"That is not allowed as a Windows folder name. Use: {cleaned}"
        return None

    def _category_for_folder(self, folder: str) -> str:
        """The existing category that already uses ``folder``, or ``folder`` as a new category."""
        for category in self.rules.categories:
            if self.rules.folder_for(category).casefold() == folder.casefold():
                return category
        return folder

    def edit_extension_destination(self, extension: str, label: str) -> None:
        current = self.rules.classify_extension(extension).folder
        choices = sorted({self.rules.folder_for(c) for c in self.rules.categories}, key=str.casefold)
        values = ask_form(
            self,
            f"Destination for {label}",
            [FormField("folder", "Destination folder", current, tuple(choices))],
            description=(
                f"Choose where {label} files go inside the destination folder. Pick an existing "
                "folder from the list, or type a new name."
            ),
            validate=self._folder_error,
        )
        if values is None:
            return
        folder = values["folder"]
        if extension == "":
            self._edit_overlay(lambda o: rules_editor.set_category_folder(o, NO_EXTENSION_CATEGORY, folder))
        else:
            category = self._category_for_folder(folder)
            self._edit_overlay(lambda o: rules_editor.set_extension_category(o, extension, category))

    def rename_category_folder(self, category: str) -> None:
        values = ask_form(
            self,
            f"Rename folder for {category}",
            [FormField("folder", "Destination folder", self.rules.folder_for(category))],
            description="The new name applies to every file type in this category.",
            validate=self._folder_error,
        )
        if values is not None:
            self._edit_overlay(lambda o: rules_editor.set_category_folder(o, category, values["folder"]))

    def reset_category_folder(self, category: str) -> None:
        self._edit_overlay(lambda o: rules_editor.clear_category_folder(o, category))

    def add_keyword_rule(self) -> None:
        def validate(values: dict[str, str]) -> str | None:
            if not values.get("keyword"):
                return "Enter a keyword."
            return self._folder_error(values)

        values = ask_form(
            self,
            "Add keyword rule",
            [FormField("keyword", "Keyword (part of a file name)"), FormField("folder", "Destination folder")],
            description="Files whose name contains the keyword go to this folder. Capital letters do not matter.",
            validate=validate,
        )
        if values is not None:
            self._edit_overlay(lambda o: rules_editor.add_keyword_rule(o, values["keyword"], values["folder"]))

    def remove_keyword_rule(self, keyword: str) -> None:
        self._edit_overlay(lambda o: rules_editor.remove_keyword_rule(o, keyword))

    def remove_extension_override(self, extension: str) -> None:
        self._edit_overlay(lambda o: rules_editor.clear_extension_override(o, extension))

    def reset_all_rules(self) -> None:
        if not messagebox.askyesno(
            APP_NAME,
            "Remove all your rule changes and go back to the built-in rules?\n\n"
            "Your current file is kept as rules.json.bak.",
            parent=self,
        ):
            return
        path = default_rules_path()
        try:
            rules_editor.backup_file(path)
            rules_editor.save_overlay(path, rules_editor.new_overlay())
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"The rules could not be reset:\n{exc}", parent=self)
            return
        self._load_rules()
        self._on_rules_changed("The rules were reset, so the preview was cleared.")

    # ----------------------------------------------------------- folders

    def choose_source(self) -> None:
        options: dict[str, Any] = {"parent": self, "title": "Choose the folder to organize", "mustexist": True}
        current = self.source_var.get().strip()
        if current and Path(current).is_dir():
            options["initialdir"] = current
        chosen = filedialog.askdirectory(**options)
        if chosen:
            self.source_var.set(os.path.normpath(chosen))

    def choose_destination(self) -> None:
        options: dict[str, Any] = {"parent": self, "title": "Choose the destination folder"}
        current = self.destination_var.get().strip()
        parent_dir = Path(current).parent if current else None
        if parent_dir is not None and parent_dir.is_dir():
            options["initialdir"] = str(parent_dir)
        chosen = filedialog.askdirectory(**options)
        if chosen:
            self.destination_var.set(os.path.normpath(chosen))

    def use_default_destination(self) -> None:
        self.settings.destination_custom = False
        self._set_destination_auto()
        self._invalidate_plan("The destination changed, so the preview was cleared.")
        self._schedule_refresh()

    def open_folder(self, text: str) -> None:
        folder = Path(text.strip()) if text.strip() else None
        if folder is None or not folder.is_dir():
            messagebox.showinfo(APP_NAME, "That folder does not exist yet.", parent=self)
            return
        try:
            os.startfile(folder)  # type: ignore[attr-defined]  # Windows only
        except (AttributeError, OSError):
            messagebox.showinfo(APP_NAME, f"Open this folder manually:\n{folder}", parent=self)

    def _set_destination_auto(self) -> None:
        source = self.source_var.get().strip()
        text = str(default_destination(source)) if source else ""
        self._suppress = True
        try:
            self.destination_var.set(text)
        finally:
            self._suppress = False

    def _on_source_edited(self, *_args: object) -> None:
        if self._suppress:
            return
        if not self.settings.destination_custom:
            self._set_destination_auto()
        self._invalidate_scan("The source folder changed. Scan again.")
        self._schedule_refresh()

    def _on_destination_edited(self, *_args: object) -> None:
        if self._suppress:
            return
        text = self.destination_var.get().strip()
        source = self.source_var.get().strip()
        automatic = str(default_destination(source)) if source else ""
        self.settings.destination_custom = bool(text) and text != automatic
        self._invalidate_plan("The destination changed, so the preview was cleared.")
        self._schedule_refresh()

    def on_scan_options_changed(self) -> None:
        self._invalidate_scan("The scan options changed. Scan again to update the results.")
        self.refresh_all()

    def _invalidate_scan(self, note: str) -> None:
        """Forget results that no longer match the chosen folder or options."""
        if self.busy:
            return
        had_results = self.scan is not None or self.scan_status is not ScanStatus.IDLE
        self.scan = None
        self.scan_progress = None
        self.scan_error = ""
        self.scan_status = ScanStatus.IDLE
        self.scan_note = note if had_results else ""
        self._reset_selection()
        self._invalidate_plan("")

    # ----------------------------------------------------------- scanning

    def start_scan(self) -> None:
        if self.busy:
            return
        source = self.source_var.get().strip()
        if not source or not Path(source).is_dir():
            messagebox.showwarning(APP_NAME, "Choose an existing source folder first.", parent=self)
            return
        destination = self.destination_var.get().strip()
        exclude = [destination] if destination else []
        recursive = bool(self.recursive_var.get())
        include_hidden = bool(self.hidden_var.get())
        rules = self.rules

        def job(progress: Any, cancelled: Any) -> ScanResult:
            return scan_directory(
                source,
                recursive=recursive,
                rules=rules,
                include_hidden=include_hidden,
                exclude_paths=exclude,
                progress=progress,
                should_cancel=cancelled,
            )

        self.scan = None
        self.scan_progress = None
        self.scan_error = ""
        self.scan_note = ""
        self._reset_selection()
        self._invalidate_plan("")
        self.scan_status = ScanStatus.SCANNING
        self._launch(
            "scan", job,
            on_progress=self._on_scan_progress, on_result=self._finish_scan, on_error=self._fail_scan,
        )
        self.refresh_all()

    def cancel_scan(self) -> None:
        if self._task_kind == "scan":
            self.cancel_task()

    def _on_scan_progress(self, progress: ScanProgress) -> None:
        self.scan_progress = progress
        dashboard = self.pages["dashboard"]
        if isinstance(dashboard, DashboardPage):
            dashboard.refresh_progress()

    def _finish_scan(self, result: ScanResult) -> None:
        self.scan = result
        self.scan_progress = None
        self.scan_status = ScanStatus.CANCELLED if result.cancelled else ScanStatus.DONE
        self._reset_selection(all_extensions(result))
        self._invalidate_plan("")
        self._save_settings()
        self.refresh_all()
        if not result.cancelled and result.files:
            self.show_page("scan")

    def _fail_scan(self, error: BaseException) -> None:
        self.scan = None
        self.scan_progress = None
        self.scan_status = ScanStatus.ERROR
        self.scan_error = f"{type(error).__name__}: {error}"
        self.refresh_all()

    # ------------------------------------------------- choosing what to include

    def current_selection(self) -> Selection:
        """What the preview and the run include: whole file types, or individual files."""
        if self.selection_mode == "files":
            return Selection(files=frozenset(self.selected_files))
        return Selection(extensions=frozenset(self.selected_extensions))

    def selection_summary(self) -> SelectionSummary | None:
        if self.scan is None:
            return None
        return summarize_selection(self.scan, self.current_selection())

    def _reset_selection(self, extensions: Iterable[str] = ()) -> None:
        self.selection_mode = "types"
        self.selected_files = set()
        self.selected_extensions = set(extensions)
        self.selection_version += 1
        self._clear_search_state()

    def _use_types_mode(self) -> None:
        self.selection_mode = "types"
        self.selected_files = set()

    def toggle_extension(self, extension: str) -> None:
        self._use_types_mode()
        if extension in self.selected_extensions:
            self.selected_extensions.discard(extension)
        else:
            self.selected_extensions.add(extension)
        self._selection_changed()

    def set_selection(self, extensions: Iterable[str]) -> None:
        self._use_types_mode()
        self.selected_extensions = set(extensions)
        self._selection_changed()
        self.refresh_all()

    def select_all_extensions(self) -> None:
        if self.scan is not None:
            self.set_selection(all_extensions(self.scan))

    def _selection_changed(self) -> None:
        self.selection_version += 1
        self._invalidate_plan("The selection changed, so the preview was cleared.")

    # ------------------------------------------------------------- find files

    def _clear_search_state(self) -> None:
        self.search_results = None
        self.found_ticked = set()
        self.found_version += 1

    def clear_search(self) -> None:
        if self.busy:
            return
        self._clear_search_state()
        self.refresh_all()

    def start_search(self, criteria: SearchCriteria) -> None:
        if self.busy or self.scan is None:
            return
        scan, rules = self.scan, self.rules

        def job(progress: Any, cancelled: Any) -> list[SearchHit]:
            return find_files(scan, criteria, rules)

        self._clear_search_state()
        self._launch("search", job, on_result=self._finish_search, on_error=self._fail_search)
        self.refresh_all()

    def _finish_search(self, hits: list[SearchHit]) -> None:
        self.search_results = hits
        self.found_ticked = {hit.key for hit in hits}  # every match starts ticked
        self.found_version += 1
        self.refresh_all()

    def _fail_search(self, error: BaseException) -> None:
        self.search_results = []
        self.found_version += 1
        self.refresh_all()
        messagebox.showerror(APP_NAME, f"The search failed:\n{type(error).__name__}: {error}", parent=self)

    def toggle_found(self, key: str) -> None:
        if key in self.found_ticked:
            self.found_ticked.discard(key)
        else:
            self.found_ticked.add(key)
        self.found_version += 1

    def set_found_ticked(self, keys: Iterable[str]) -> None:
        self.found_ticked = set(keys)
        self.found_version += 1
        self.refresh_all()

    def use_found_files(self) -> None:
        """Make the ticked search results the selection, then show the preview."""
        if self.busy or self.scan is None or not self.found_ticked:
            return
        self.selection_mode = "files"
        self.selected_files = set(self.found_ticked)
        self._selection_changed()
        self.refresh_all()
        self.show_page("preview")

    # ------------------------------------------------------------- preview

    def _plan_options(self):
        return plan_options(self.action_label, self.conflict_label, self.layout_label)

    def _invalidate_plan(self, note: str = "") -> None:
        self._plan_version += 1
        self.plan = None
        self.plan_status = PlanStatus.NONE
        self.plan_error = ""
        self.plan_note = note

    def set_plan_option(self, kind: str, label: str) -> None:
        if self.busy:
            return
        if kind == "action":
            self.action_label = label
        elif kind == "conflict":
            self.conflict_label = label
        elif kind == "layout":
            self.layout_label = label
        self._invalidate_plan("")
        self.refresh_preview()

    def _maybe_build_preview(self) -> None:
        if self.busy or self.scan is None or self.plan is not None:
            return
        if self.plan_status is PlanStatus.ERROR or not self.has_selection:
            return
        self.refresh_preview()

    def refresh_preview(self) -> None:
        """Build the preview for the selection (reads the disk, changes nothing)."""
        if self.busy or self.scan is None:
            return
        if not self.has_selection:
            self._invalidate_plan("Nothing is selected.")
            self.refresh_all()
            return
        destination = self.destination_var.get().strip()
        check = validate_paths(self.scan.source, destination)
        if not check.ok:
            self.plan = None
            self.plan_status = PlanStatus.ERROR
            self.plan_error = " ".join(check.errors)
            self.refresh_all()
            return

        scan, rules, options = self.scan, self.rules, self._plan_options()
        selection = self.current_selection()
        version = self._plan_version

        def job(progress: Any, cancelled: Any) -> Plan:
            return jobs.build_preview(scan, selection, rules, destination, options)

        self.plan = None
        self.plan_status = PlanStatus.BUILDING
        self.plan_error = ""
        self.plan_note = ""
        self._launch(
            "preview", job,
            on_result=lambda plan, v=version: self._finish_preview(plan, v),
            on_error=self._fail_preview,
        )
        self.refresh_all()

    def _finish_preview(self, plan: Plan, version: int) -> None:
        if version != self._plan_version:  # the inputs changed while it was being built
            self.plan_status = PlanStatus.NONE
            self.refresh_all()
            if self._current_page == "preview":
                self._maybe_build_preview()
            return
        self.plan = plan
        self.plan_status = PlanStatus.READY
        self.refresh_all()

    def _fail_preview(self, error: BaseException) -> None:
        self.plan = None
        self.plan_status = PlanStatus.ERROR
        if isinstance(error, PlanValidationError):
            self.plan_error = " ".join(error.errors)
        else:
            self.plan_error = f"{type(error).__name__}: {error}"
        self.refresh_all()

    # ----------------------------------------------------------------- run

    def request_run(self) -> None:
        plan = self.plan
        if self.busy or plan is None or self.scan is None:
            return
        if not plan.executable_items:
            messagebox.showinfo(APP_NAME, "There is nothing to do in this preview.", parent=self)
            return
        if not messagebox.askyesno(APP_NAME, confirmation_text(plan), icon="warning", parent=self):
            return
        self._start_run(plan)

    def _start_run(self, plan: Plan) -> None:
        scan = self.scan
        if scan is None:
            return
        selection = self.current_selection()
        rules, history = self.rules, self.history
        destination, options = str(plan.destination), plan.options

        def job(progress: Any, cancelled: Any) -> jobs.RunJobResult:
            return jobs.run_plan_job(
                scan, selection, rules, destination, options, plan, history,
                progress=progress, should_cancel=cancelled,
            )

        self.run_status = RunStatus.RUNNING
        self.run_progress = None
        self.run_result = None
        self.run_plan = plan
        self.run_error = ""
        if self._launch(
            "run", job,
            on_progress=self._on_run_progress, on_result=self._finish_run, on_error=self._fail_run,
        ):
            self.refresh_all()
            self.show_page("run")

    def _on_run_progress(self, progress: ExecutionProgress) -> None:
        self.run_progress = progress
        self.run_page.refresh_progress()

    def _finish_run(self, outcome: jobs.RunJobResult) -> None:
        if outcome.changed_plan is not None:
            self.plan = outcome.changed_plan
            self.plan_status = PlanStatus.READY
            self.run_status = RunStatus.IDLE
            self.run_plan = None
            self.refresh_all()
            self.show_page("preview")
            messagebox.showinfo(
                APP_NAME,
                "The destination folder changed after the preview was built, so nothing was run.\n\n"
                "The preview has been refreshed. Review it and press Run again.",
                parent=self,
            )
            return
        result = outcome.result
        self.run_result = result
        self.run_status = RunStatus.FINISHED
        self.run_progress = None
        self._invalidate_plan("")
        if result is not None and result.succeeded and self.run_plan is not None:
            self._mark_scan_stale("Files were organized. Scan again to see the current folder contents.")
        self.reload_history()
        self.refresh_all()

    def _fail_run(self, error: BaseException) -> None:
        self.run_status = RunStatus.ERROR
        if isinstance(error, PlanValidationError):
            self.run_error = " ".join(error.errors)
        else:
            self.run_error = f"{type(error).__name__}: {error}"
        self._invalidate_plan("")
        self.reload_history()
        self.refresh_all()

    def _mark_scan_stale(self, note: str) -> None:
        self.scan = None
        self.scan_progress = None
        self.scan_status = ScanStatus.IDLE
        self.scan_note = note
        self._reset_selection()

    def save_run_report(self) -> None:
        result, plan = self.run_result, self.run_plan
        if result is None or plan is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Save report", defaultextension=".txt",
            initialfile=f"report-{result.run_id}.txt", filetypes=[("Text file", "*.txt")],
        )
        if not path:
            return
        try:
            Path(path).write_text(report_text(result, plan) + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"The report could not be saved:\n{exc}", parent=self)
            return
        messagebox.showinfo(APP_NAME, f"Report saved:\n{path}", parent=self)

    # ------------------------------------------------------------- history

    def reload_history(self) -> None:
        try:
            self.history_runs = self.history.list_runs()
            self.history_error = ""
        except OSError as exc:
            self.history_runs = []
            self.history_error = str(exc)

    def reload_history_and_refresh(self) -> None:
        self.reload_history()
        self.refresh_all()

    def show_run_details(self, run_id: str) -> None:
        try:
            run = self.history.load_run(run_id)
        except HistoryError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        TextDialog(self, f"Run {run_id}", run_details_text(run))

    def export_run_csv(self, run_id: str) -> None:
        try:
            run = self.history.load_run(run_id)
        except HistoryError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Export run as CSV", defaultextension=".csv",
            initialfile=f"{run_id}.csv", filetypes=[("CSV file", "*.csv")],
        )
        if not path:
            return
        try:
            export_run_csv(run, path)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"The file could not be saved:\n{exc}", parent=self)
            return
        messagebox.showinfo(APP_NAME, f"Exported:\n{path}", parent=self)

    # ---------------------------------------------------------------- undo

    def start_undo(self, run_id: str) -> None:
        if self.busy:
            return
        history = self.history
        self.undo_message = ""

        def job(progress: Any, cancelled: Any) -> jobs.UndoPreflight:
            return jobs.undo_preflight(history, run_id)

        self._launch(
            "undo_check", job,
            on_result=lambda pre, r=run_id: self._after_preflight(r, pre),
            on_error=lambda error: self._undo_failed(error),
        )
        self.refresh_all()

    def _after_preflight(self, run_id: str, pre: jobs.UndoPreflight) -> None:
        summary = preflight_summary(pre.checks)
        if summary.ok == 0:
            reasons = "\n".join(f"  \u2022 {reason}" for reason in summary.reasons)
            detail = f"\n\nWhy:\n{reasons}" if reasons else ""
            messagebox.showinfo(APP_NAME, f"Nothing from this run can be undone right now.{detail}", parent=self)
            self.undo_message = "Nothing could be undone for that run."
            self.refresh_all()
            return
        if not messagebox.askyesno(
            APP_NAME, undo_confirmation_text(summary, pre.run.action), icon="warning", parent=self
        ):
            self.refresh_all()
            return
        self._run_undo(run_id)

    def _run_undo(self, run_id: str) -> None:
        history = self.history
        self.undo_progress = None

        def job(progress: Any, cancelled: Any) -> UndoResult:
            return undo_run(history, run_id, progress=progress, should_cancel=cancelled)

        self._launch(
            "undo", job,
            on_progress=self._on_undo_progress, on_result=self._finish_undo, on_error=self._undo_failed,
        )
        self.refresh_all()

    def _on_undo_progress(self, progress: UndoProgress) -> None:
        self.undo_progress = progress
        self.history_page.refresh_progress()

    def _finish_undo(self, result: UndoResult) -> None:
        self.undo_progress = None
        self.undo_message = (
            f"Undo finished: {result.undone:,} restored, {result.blocked:,} left alone, {result.failed:,} failed."
        )
        self._invalidate_plan("")
        if result.undone:
            self._mark_scan_stale("Files were restored. Scan again to see the current folder contents.")
        self.reload_history()
        self.refresh_all()
        TextDialog(self, "Undo report", undo_report_text(result))

    def _undo_failed(self, error: BaseException) -> None:
        self.undo_progress = None
        self.undo_message = f"Undo failed: {type(error).__name__}: {error}"
        self.reload_history()
        self.refresh_all()

    # ------------------------------------------------------------ settings

    def apply_appearance(self, mode: str) -> None:
        if mode not in APPEARANCE_MODES:
            return
        ctk.set_appearance_mode(mode)
        self.settings.appearance = mode
        self._save_settings()
        self.after(80, lambda: apply_treeview_style(self.ui_scale))

    def set_ui_scale(self, percent: int) -> None:
        if percent == self.settings.ui_scale:
            return
        self.settings.ui_scale = percent
        self._save_settings()
        messagebox.showinfo(APP_NAME, "Restart the application to apply the new interface size.", parent=self)

    def _save_settings(self) -> None:
        settings = self.settings
        settings.source = self.source_var.get().strip()
        settings.destination = self.destination_var.get().strip()
        settings.recursive = bool(self.recursive_var.get())
        settings.include_hidden = bool(self.hidden_var.get())
        try:
            self.store.save(settings)
        except OSError:
            logger.warning("Settings could not be saved", exc_info=True)

    # ------------------------------------------------------------ lifecycle

    def _on_close(self) -> None:
        if self._task_kind in ("run", "undo"):
            messagebox.showwarning(
                APP_NAME,
                "A file operation is still running.\n\nPress Cancel on the Run or History page "
                "(it stops after the current file) and close the window when it has finished.",
                parent=self,
            )
            return
        if self._task is not None:
            self._task.cancel()
        for after_id in (self._poll_id, self._refresh_id):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        self._save_settings()
        self.destroy()

    def _report_callback_exception(self, exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        logger.error("Unhandled error in the interface", exc_info=(exc_type, exc_value, exc_tb))
        if self._dialog_open:
            return
        self._dialog_open = True
        try:
            where = f"\n\nDetails were written to:\n{self.log_path}" if self.log_path else ""
            messagebox.showerror(
                APP_NAME,
                f"An unexpected error occurred.\n\n{exc_type.__name__}: {exc_value}{where}",
                parent=self,
            )
        finally:
            self._dialog_open = False


def _configure_logging() -> Path | None:
    """Log to a rotating file in the user's data folder. Returns its path, or None."""
    try:
        directory = default_log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "smartfileorganizer.log"
        handler = RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=2, encoding="utf-8")
    except OSError:
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    package_logger = logging.getLogger("organizer")
    package_logger.setLevel(logging.INFO)
    package_logger.addHandler(handler)
    return path


def _show_fatal(message: str) -> None:
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, message)
        root.destroy()
    except tk.TclError:
        pass


def run() -> int:
    """Start the application. Returns a process exit code."""
    log_path = _configure_logging()
    store = SettingsStore()
    settings = store.load()
    ctk.set_appearance_mode(settings.appearance)
    ctk.set_default_color_theme("blue")
    scale = settings.ui_scale / 100
    ctk.set_widget_scaling(scale)
    ctk.set_window_scaling(scale)
    try:
        app = App(store, settings, log_path)
    except Exception as exc:
        logger.exception("The application could not start")
        where = f"\n\nDetails were written to:\n{log_path}" if log_path else ""
        _show_fatal(f"{APP_NAME} could not start.\n\n{type(exc).__name__}: {exc}{where}")
        return 1
    app.mainloop()
    return 0