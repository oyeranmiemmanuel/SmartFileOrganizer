"""Scan Results: choose which file types to include and where each type goes."""

from __future__ import annotations

from tkinter import messagebox
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from ..formatting import format_bytes, format_count, plural, shorten_path
from ..planner import ExtensionSummary, extension_summary
from ..selection import summarize_selection
from .state import ScanStatus, issues_text, summarize_skipped
from .theme import APP_NAME, MUTED, font, labeled
from .widgets import (
    Column,
    DataTable,
    Page,
    TextDialog,
    primary_button_style,
    secondary_button_style,
)

if TYPE_CHECKING:
    from ..app import App

_PREFIX = "ext:"


def _checkbox(value: Any) -> str:
    return "☑" if value else "☐"


class ScanPage(Page):
    def __init__(self, master: Any, app: "App") -> None:
        super().__init__(master, app)
        self._render_key: tuple[Any, ...] | None = None
        self._summaries: dict[str, ExtensionSummary] = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Scan Results", font=font(26, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        self.summary = ctk.CTkLabel(header, text="", text_color=MUTED, anchor="w", justify="left", wraplength=820)
        self.summary.grid(row=1, column=0, sticky="w", pady=(2, 0))
        ctk.CTkLabel(
            header,
            text="Tick the file types to include. Double-click a row to choose where that type goes.",
            text_color=MUTED, anchor="w", font=font(12),
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        toolbar.grid_columnconfigure(0, weight=1)
        self.search = ctk.CTkEntry(
            toolbar, placeholder_text="Filter by extension, category or folder…", height=36
        )
        self.search.grid(row=0, column=0, sticky="ew")
        self.search.bind("<KeyRelease>", self._on_filter)
        for column, (text, command) in enumerate(
            (
                ("Select all", self._select_all),
                ("Select none", self._select_none),
                ("Only visible", self._select_visible),
            ),
            start=1,
        ):
            ctk.CTkButton(
                toolbar, text=text, command=command, height=36, width=100, **secondary_button_style()
            ).grid(row=0, column=column, padx=(8, 0))

        self.table = DataTable(
            self,
            [
                Column("include", "Include", width=80, anchor="center", formatter=_checkbox, searchable=False),
                Column("extension", "Extension", width=120),
                Column("count", "Files", width=80, anchor="e", formatter=format_count, searchable=False),
                Column("size", "Total size", width=100, anchor="e", formatter=format_bytes, searchable=False),
                Column("category", "Category", width=170),
                Column("folder", "Destination folder", width=220, stretch=True),
            ],
            row_id=lambda row: _PREFIX + row[6],
            on_click=self._on_cell_click,
            on_double_click=self._on_cell_double_click,
            on_space=self._toggle_by_id,
        )
        self.table.grid(row=2, column=0, sticky="nsew")

        self.empty = ctk.CTkFrame(self, fg_color="transparent")
        self.empty.grid_columnconfigure(0, weight=1)
        self.empty_label = ctk.CTkLabel(
            self.empty, text="", text_color=MUTED, font=font(14), justify="center", wraplength=600
        )
        self.empty_label.grid(row=0, column=0, pady=(60, 12))
        ctk.CTkButton(
            self.empty, text=labeled("dashboard", "Go to Dashboard"),
            command=lambda: app.show_page("dashboard"), width=180, height=38, **primary_button_style(),
        ).grid(row=1, column=0)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        self.selection_label = ctk.CTkLabel(bottom, text="", anchor="w", font=font(13, "bold"))
        self.selection_label.grid(row=0, column=0, sticky="w")
        self.destination_button = ctk.CTkButton(
            bottom, text=labeled("rules", "Change destination…"), command=self._edit_destination,
            height=36, **secondary_button_style(),
        )
        self.destination_button.grid(row=0, column=1, padx=(8, 0))
        self.details_button = ctk.CTkButton(
            bottom, text="Skipped & errors…", command=self._show_details, height=36, **secondary_button_style()
        )
        self.details_button.grid(row=0, column=2, padx=(8, 0))
        self.rescan_button = ctk.CTkButton(
            bottom, text=labeled("scan", "Rescan"), command=app.start_scan, height=36, width=100,
            **secondary_button_style(),
        )
        self.rescan_button.grid(row=0, column=3, padx=(8, 0))
        self.next_button = ctk.CTkButton(
            bottom, text=labeled("preview", "Continue to Preview"), command=lambda: app.show_page("preview"),
            height=36, **primary_button_style(),
        )
        self.next_button.grid(row=0, column=4, padx=(8, 0))

        self.footer = ctk.CTkLabel(
            self, text="", text_color=MUTED, anchor="w", justify="left", wraplength=820, font=font(12)
        )
        self.footer.grid(row=4, column=0, sticky="ew", pady=(6, 0))

    # ------------------------------------------------------------- rows

    def _row(self, summary: ExtensionSummary) -> tuple[Any, ...]:
        return (
            summary.extension in self.app.selected_extensions,
            summary.label,
            summary.count,
            summary.total_size,
            summary.category,
            summary.folder,
            summary.extension,
        )

    def _current_key(self) -> tuple[Any, ...]:
        app = self.app
        return (id(app.scan), id(app.rules), app.selection_version)

    # ----------------------------------------------------------- refreshing

    def refresh(self) -> None:
        app = self.app
        scan = app.scan
        self.rescan_button.configure(state="disabled" if app.busy else "normal")
        if scan is None:
            self._show_empty()
            return

        self.empty.grid_remove()
        self.table.grid(row=2, column=0, sticky="nsew")
        self.details_button.configure(state="normal" if (scan.skipped or scan.errors) else "disabled")

        key = self._current_key()
        if key != self._render_key:
            self._summaries = {row.extension: row for row in extension_summary(scan, app.rules)}
            self.table.set_rows([self._row(summary) for summary in self._summaries.values()])
            self._render_key = key

        partial = " · partial: the scan was cancelled" if scan.cancelled else ""
        self.summary.configure(
            text=(
                f"{plural(len(scan.files), 'file')} · {plural(len(self._summaries), 'extension')} · "
                f"{format_bytes(scan.total_size)} · {shorten_path(str(scan.source), 70)}{partial}"
            )
        )
        pieces = [f"{count:,} {label}" for label, count in summarize_skipped(scan.skipped)]
        footer = "Skipped: " + ", ".join(pieces) + "." if pieces else ""
        if scan.errors:
            footer += f" {plural(len(scan.errors), 'item')} could not be read."
        footer += " Keyword rules apply per file in the preview, so they are not shown here."
        self.footer.configure(text=footer.strip())
        self._update_labels()

    def _update_labels(self) -> None:
        app = self.app
        scan = app.scan
        if scan is None:
            return
        selection = summarize_selection(scan, app.current_selection())
        if app.selection_mode == "files":
            text = (
                f"{plural(selection.files, 'individual file')} from Find Files · "
                f"{format_bytes(selection.size)}"
            )
        else:
            text = (
                f"{selection.extensions} of {selection.total_extensions} file types selected · "
                f"{plural(selection.files, 'file')} ({format_bytes(selection.size)})"
            )
        self.selection_label.configure(text=text)
        self.next_button.configure(state="normal" if selection.files and not app.busy else "disabled")
        self.destination_button.configure(state="normal" if not app.busy else "disabled")

    def _show_empty(self) -> None:
        app = self.app
        self._render_key = None
        self.table.grid_remove()
        self.empty.grid(row=2, column=0, sticky="nsew")
        self.details_button.configure(state="disabled")
        self.next_button.configure(state="disabled")
        self.destination_button.configure(state="disabled")
        self.selection_label.configure(text="")
        self.summary.configure(text="")
        self.footer.configure(text="")
        status = app.scan_status
        if status is ScanStatus.SCANNING:
            text = "Scanning… the results will appear here when the scan finishes."
        elif status is ScanStatus.ERROR:
            text = f"The scan failed.\n{app.scan_error}"
        elif app.scan_note:
            text = app.scan_note
        else:
            text = "No scan results yet. Choose a source folder on the Dashboard and press Scan folder."
        self.empty_label.configure(text=text)

    # -------------------------------------------------------------- actions

    def _on_filter(self, _event: Any = None) -> None:
        self.table.set_filter(self.search.get())

    def _toggle_by_id(self, row_id: str) -> None:
        extension = row_id[len(_PREFIX):]
        self.app.toggle_extension(extension)
        summary = self._summaries.get(extension)
        if summary is not None:
            self.table.update_row(self._row(summary))
        self._render_key = self._current_key()
        self._update_labels()

    def _on_cell_click(self, row_id: str, column: str) -> None:
        if column == "include":
            self._toggle_by_id(row_id)

    def _on_cell_double_click(self, row_id: str, column: str) -> None:
        if column != "include":
            self._edit(row_id)

    def _select_all(self) -> None:
        self.app.select_all_extensions()

    def _select_none(self) -> None:
        self.app.set_selection([])

    def _select_visible(self) -> None:
        self.app.set_selection(row_id[len(_PREFIX):] for row_id in self.table.visible_ids())

    def _edit_destination(self) -> None:
        row_id = self.table.selected_id()
        if row_id is None:
            messagebox.showinfo(APP_NAME, "Select a file type in the table first.", parent=self.app)
            return
        self._edit(row_id)

    def _edit(self, row_id: str) -> None:
        extension = row_id[len(_PREFIX):]
        summary = self._summaries.get(extension)
        label = summary.label if summary else extension
        self.app.edit_extension_destination(extension, label)

    def _show_details(self) -> None:
        scan = self.app.scan
        if scan is not None:
            TextDialog(self.app, "Skipped items and errors", issues_text(scan))