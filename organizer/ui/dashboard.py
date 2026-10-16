"""Dashboard: choose folders, set scan options, scan, and see the headline numbers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from ..formatting import format_bytes, format_count, plural, shorten_path
from .state import ScanStatus, status_badge, validation_messages
from .theme import MUTED, font, labeled
from .widgets import (
    Card,
    MessageList,
    Page,
    PathField,
    StatCard,
    StatusBadge,
    primary_button_style,
    secondary_button_style,
)

if TYPE_CHECKING:
    from ..app import App


class DashboardPage(Page):
    def __init__(self, master: Any, app: "App") -> None:
        super().__init__(master, app)
        self._bar_running = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Dashboard", font=font(26, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        self.badge = StatusBadge(header)
        self.badge.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(
            header,
            text="Choose a folder and scan it. Scanning only reads your files; it never changes them.",
            text_color=MUTED,
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        self._build_stats(body)
        self._build_folders(body)
        self._build_options(body)
        self._build_scan(body)
        self._build_rules(body)

    # ------------------------------------------------------------ building

    def _build_stats(self, body: Any) -> None:
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew")
        self.stat_files = StatCard(row, "Files found")
        self.stat_types = StatCard(row, "File types")
        self.stat_size = StatCard(row, "Total size")
        self.stat_skipped = StatCard(row, "Skipped items")
        for column, card in enumerate((self.stat_files, self.stat_types, self.stat_size, self.stat_skipped)):
            row.grid_columnconfigure(column, weight=1, uniform="stats")
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0 if column == 3 else 6))

    def _build_folders(self, body: Any) -> None:
        app = self.app
        card = Card(body, "Folders")
        card.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self.source_field = PathField(
            card.body, "Source folder (the folder to organize)", app.source_var, app.choose_source,
            extras=[(labeled("open", "Open"), lambda: app.open_folder(app.source_var.get()))],
        )
        self.source_field.grid(row=0, column=0, sticky="ew")
        self.destination_field = PathField(
            card.body, "Destination folder (where organized files will go)", app.destination_var,
            app.choose_destination,
            extras=[
                ("Default", app.use_default_destination),
                (labeled("open", "Open"), lambda: app.open_folder(app.destination_var.get())),
            ],
        )
        self.destination_field.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self.messages = MessageList(card.body)
        self.messages.grid(row=2, column=0, sticky="ew", pady=(12, 0))

    def _build_options(self, body: Any) -> None:
        app = self.app
        card = Card(body, "Scan options")
        card.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self.recursive_switch = ctk.CTkSwitch(
            card.body, text="Include subfolders", variable=app.recursive_var,
            command=app.on_scan_options_changed,
        )
        self.recursive_switch.grid(row=0, column=0, sticky="w")
        self.hidden_switch = ctk.CTkSwitch(
            card.body, text="Include hidden files and folders", variable=app.hidden_var,
            command=app.on_scan_options_changed,
        )
        self.hidden_switch.grid(row=1, column=0, sticky="w", pady=(10, 0))
        ctk.CTkLabel(
            card.body,
            text=(
                "Folders such as .git, node_modules and $RECYCLE.BIN are always skipped when scanning "
                "subfolders. Links, junctions and Windows system items are never followed."
            ),
            text_color=MUTED, anchor="w", justify="left", wraplength=700, font=font(12),
        ).grid(row=2, column=0, sticky="w", pady=(10, 0))

    def _build_scan(self, body: Any) -> None:
        app = self.app
        card = Card(body, "Scan")
        card.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        buttons = ctk.CTkFrame(card.body, fg_color="transparent")
        buttons.grid(row=0, column=0, sticky="w")
        self.scan_button = ctk.CTkButton(
            buttons, text=labeled("scan", "Scan folder"), command=app.start_scan, height=40, width=170,
            font=font(14, "bold"), **primary_button_style(),
        )
        self.scan_button.grid(row=0, column=0)
        self.cancel_button = ctk.CTkButton(
            buttons, text=labeled("stop", "Cancel"), command=app.cancel_scan, height=40, width=120,
            **secondary_button_style(),
        )
        self.cancel_button.grid(row=0, column=1, padx=(10, 0))
        self.bar = ctk.CTkProgressBar(card.body, mode="determinate", height=10)
        self.bar.set(0)
        self.bar.grid(row=1, column=0, sticky="ew", pady=(14, 6))
        self.progress_label = ctk.CTkLabel(
            card.body, text="", anchor="w", justify="left", text_color=MUTED, wraplength=700, font=font(12)
        )
        self.progress_label.grid(row=2, column=0, sticky="ew")

    def _build_rules(self, body: Any) -> None:
        card = Card(body, "Classification rules")
        card.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        self.rules_messages = MessageList(card.body)
        self.rules_messages.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            card.body, text="Change how files are classified in Settings.", text_color=MUTED, anchor="w",
            font=font(12),
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

    # ----------------------------------------------------------- refreshing

    def refresh(self) -> None:
        app = self.app
        status = app.scan_status
        scanning = status is ScanStatus.SCANNING
        text, kind = status_badge(status, app.cancelling)
        self.badge.set(text, kind)

        source = app.source_var.get().strip()
        destination = app.destination_var.get().strip()
        self.messages.set(validation_messages(source, destination))
        source_ok = bool(source) and Path(source).is_dir()

        locked = app.busy
        enabled = "disabled" if locked else "normal"
        self.source_field.set_enabled(not locked)
        self.destination_field.set_enabled(not locked)
        self.recursive_switch.configure(state=enabled)
        self.hidden_switch.configure(state=enabled)
        self.scan_button.configure(state="normal" if source_ok and not locked else "disabled")
        self.cancel_button.configure(state="normal" if scanning and not app.cancelling else "disabled")
        self._update_stats()
        self._update_progress_text()
        self._update_bar()
        self._update_rules()

    def refresh_progress(self) -> None:
        """Lightweight update used while a scan is running."""
        self._update_stats()
        self._update_progress_text()

    def _update_stats(self) -> None:
        app = self.app
        scan = app.scan
        if scan is not None:
            types = len({item.extension for item in scan.files})
            self.stat_files.set(format_count(len(scan.files)), f"in {plural(scan.directories_scanned, 'folder')}")
            self.stat_types.set(format_count(types), "different extensions")
            self.stat_size.set(format_bytes(scan.total_size))
            problems = f"{plural(len(scan.errors), 'error')}" if scan.errors else ""
            self.stat_skipped.set(format_count(len(scan.skipped)), problems)
        elif app.scan_status is ScanStatus.SCANNING and app.scan_progress is not None:
            progress = app.scan_progress
            self.stat_files.set(format_count(progress.files_found), "so far")
            self.stat_types.set("—")
            self.stat_size.set("—")
            self.stat_skipped.set("—")
        else:
            for card in (self.stat_files, self.stat_types, self.stat_size, self.stat_skipped):
                card.set("—")

    def _update_progress_text(self) -> None:
        app = self.app
        status = app.scan_status
        if status is ScanStatus.SCANNING:
            progress = app.scan_progress
            if app.cancelling:
                text = "Cancelling… the scan stops at the next folder entry."
            elif progress is None:
                text = "Starting the scan…"
            else:
                text = (
                    f"Scanning… {plural(progress.files_found, 'file')} in "
                    f"{plural(progress.directories_scanned, 'folder')}\n"
                    f"{shorten_path(str(progress.current_directory), 90)}"
                )
        elif status is ScanStatus.DONE and app.scan is not None:
            text = f"Finished: {plural(len(app.scan.files), 'file')} found. Open Scan Results to review them."
        elif status is ScanStatus.CANCELLED and app.scan is not None:
            text = f"Cancelled. {plural(len(app.scan.files), 'file')} found so far; the results are partial."
        elif status is ScanStatus.ERROR:
            text = f"The scan failed: {app.scan_error}"
        else:
            text = app.scan_note
        self.progress_label.configure(text=text)

    def _update_bar(self) -> None:
        status = self.app.scan_status
        if status is ScanStatus.SCANNING:
            if not self._bar_running:
                self.bar.configure(mode="indeterminate")
                self.bar.start()
                self._bar_running = True
            return
        if self._bar_running:
            self.bar.stop()
            self.bar.configure(mode="determinate")
            self._bar_running = False
        self.bar.set(1 if status is ScanStatus.DONE else 0)

    def _update_rules(self) -> None:
        app = self.app
        messages: list[tuple[str, str]] = [("ok", f"Using {app.rules_origin}.")]
        if app.rules_error:
            messages = [("error", f"{app.rules_error} The built-in rules are being used instead.")]
        for warning in app.rules_warnings[:4]:
            messages.append(("warning", warning))
        if len(app.rules_warnings) > 4:
            messages.append(("muted", f"... and {len(app.rules_warnings) - 4} more warnings."))
        self.rules_messages.set(messages)