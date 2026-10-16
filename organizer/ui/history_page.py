"""History: past runs (kept across restarts), their details, CSV export and undo."""

from __future__ import annotations

from tkinter import messagebox
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from ..formatting import format_count, shorten_path
from .operation_state import history_row
from .theme import APP_NAME, MUTED, font, labeled
from .widgets import (
    Column,
    DataTable,
    Page,
    primary_button_style,
    secondary_button_style,
)

if TYPE_CHECKING:
    from ..app import App


class HistoryPage(Page):
    def __init__(self, master: Any, app: "App") -> None:
        super().__init__(master, app)
        self._render_key: int | None = None
        self._bar_mode = "determinate"
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="History", font=font(26, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Every run is recorded. Select one to see its details, export it, or undo it.",
            text_color=MUTED, anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.refresh_button = ctk.CTkButton(
            header, text=labeled("scan", "Refresh"), command=app.reload_history_and_refresh, height=34, width=100,
            **secondary_button_style(),
        )
        self.refresh_button.grid(row=0, column=1, rowspan=2, sticky="e")

        self.note = ctk.CTkLabel(self, text="", text_color=MUTED, anchor="w", font=font(12))
        self.note.grid(row=1, column=0, sticky="w")

        self.table = DataTable(
            self,
            [
                Column("started", "Started", width=150),
                Column("action", "Action", width=70),
                Column("source", "Source", width=210),
                Column("destination", "Destination", width=210, stretch=True),
                Column("done", "Done", width=60, anchor="e", formatter=format_count, searchable=False),
                Column("skipped", "Skipped", width=70, anchor="e", formatter=format_count, searchable=False),
                Column("failed", "Failed", width=60, anchor="e", formatter=format_count, searchable=False),
                Column("undone", "Undone", width=70, anchor="e", formatter=format_count, searchable=False),
                Column("status", "Status", width=100),
            ],
            row_id=lambda row: str(row[9]),
        )
        self.table.grid(row=2, column=0, sticky="nsew")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.details_button = ctk.CTkButton(
            actions, text=labeled("info", "Details…"), command=self._details, height=36, **secondary_button_style()
        )
        self.details_button.grid(row=0, column=0)
        self.csv_button = ctk.CTkButton(
            actions, text=labeled("export", "Export CSV…"), command=self._export, height=36,
            **secondary_button_style(),
        )
        self.csv_button.grid(row=0, column=1, padx=(8, 0))
        self.undo_button = ctk.CTkButton(
            actions, text=labeled("undo", "Undo…"), command=self._undo, height=36, **primary_button_style()
        )
        self.undo_button.grid(row=0, column=2, padx=(8, 0))

        progress = ctk.CTkFrame(self, fg_color="transparent")
        progress.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        progress.grid_columnconfigure(0, weight=1)
        self.bar = ctk.CTkProgressBar(progress, mode="determinate", height=10)
        self.bar.set(0)
        self.bar.grid(row=0, column=0, sticky="ew")
        self.cancel_button = ctk.CTkButton(
            progress, text=labeled("stop", "Cancel undo"), command=app.cancel_task, height=30, width=110,
            **secondary_button_style(),
        )
        self.cancel_button.grid(row=0, column=1, padx=(12, 0))
        self.status_label = ctk.CTkLabel(
            progress, text="", anchor="w", justify="left", text_color=MUTED, wraplength=820, font=font(12)
        )
        self.status_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    # ----------------------------------------------------------- refreshing

    def refresh(self) -> None:
        app = self.app
        if self._render_key != id(app.history_runs):
            self._render_key = id(app.history_runs)
            self.table.set_rows([history_row(summary) for summary in app.history_runs])
        if app.history_error:
            self.note.configure(text=f"The history folder could not be read: {app.history_error}")
        elif not app.history_runs:
            self.note.configure(text="No operations have been run yet.")
        else:
            self.note.configure(text="")

        busy = app.busy
        state = "disabled" if busy else "normal"
        self.refresh_button.configure(state=state)
        self.details_button.configure(state="normal" if app.history_runs else "disabled")
        self.csv_button.configure(state="normal" if app.history_runs else "disabled")
        self.undo_button.configure(state=state if app.history_runs else "disabled")
        self.cancel_button.configure(
            state="normal" if app.task_kind == "undo" and not app.cancelling else "disabled"
        )
        self._update_status()

    def refresh_progress(self) -> None:
        self._update_status()

    def _set_bar(self, mode: str, value: float = 0.0) -> None:
        if mode == "indeterminate":
            if self._bar_mode != "indeterminate":
                self.bar.configure(mode="indeterminate")
                self.bar.start()
        else:
            if self._bar_mode == "indeterminate":
                self.bar.stop()
                self.bar.configure(mode="determinate")
            self.bar.set(value)
        self._bar_mode = mode

    def _update_status(self) -> None:
        app = self.app
        if app.task_kind == "undo_check":
            self._set_bar("indeterminate")
            self.status_label.configure(text="Checking which files can be undone…")
        elif app.task_kind == "undo":
            progress = app.undo_progress
            if progress is None:
                self._set_bar("determinate", 0.0)
                self.status_label.configure(text="Undoing…")
            else:
                fraction = progress.completed / progress.total if progress.total else 0.0
                self._set_bar("determinate", fraction)
                current = f"\n{shorten_path(progress.current, 90)}" if progress.current else ""
                self.status_label.configure(
                    text=(
                        f"Undoing {progress.completed:,} of {progress.total:,} · "
                        f"{progress.undone:,} restored · {progress.blocked:,} left alone{current}"
                    )
                )
        else:
            self._set_bar("determinate", 0.0)
            self.status_label.configure(text=app.undo_message)

    # -------------------------------------------------------------- actions

    def _selected_run(self) -> str | None:
        run_id = self.table.selected_id()
        if run_id is None:
            messagebox.showinfo(APP_NAME, "Select a run in the table first.", parent=self.app)
        return run_id

    def _details(self) -> None:
        run_id = self._selected_run()
        if run_id:
            self.app.show_run_details(run_id)

    def _export(self) -> None:
        run_id = self._selected_run()
        if run_id:
            self.app.export_run_csv(run_id)

    def _undo(self) -> None:
        run_id = self._selected_run()
        if run_id:
            self.app.start_undo(run_id)