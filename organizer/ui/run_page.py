"""Run & Report: live progress of the current operation and its final report."""

from __future__ import annotations

from tkinter import messagebox
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from ..formatting import format_bytes, plural, shorten_path
from ..planner import Action
from ..reports import problem_rows
from .operation_state import RunStatus, run_badge
from .state import ScanStatus  # noqa: F401  (kept for symmetry with other pages)
from .theme import APP_NAME, MUTED, font, labeled
from .widgets import (
    Column,
    DataTable,
    Page,
    StatCard,
    StatusBadge,
    primary_button_style,
    secondary_button_style,
)

if TYPE_CHECKING:
    from ..app import App


class RunPage(Page):
    def __init__(self, master: Any, app: "App") -> None:
        super().__init__(master, app)
        self._render_key: int | None = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Run & Report", font=font(26, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        self.badge = StatusBadge(header)
        self.badge.grid(row=0, column=1, sticky="e")

        progress = ctk.CTkFrame(self, fg_color="transparent")
        progress.grid(row=1, column=0, sticky="ew")
        progress.grid_columnconfigure(0, weight=1)
        self.bar = ctk.CTkProgressBar(progress, mode="determinate", height=12)
        self.bar.set(0)
        self.bar.grid(row=0, column=0, sticky="ew", pady=(4, 6))
        self.progress_label = ctk.CTkLabel(
            progress, text="", anchor="w", justify="left", text_color=MUTED, wraplength=820, font=font(12)
        )
        self.progress_label.grid(row=1, column=0, sticky="ew")
        self.cancel_button = ctk.CTkButton(
            progress, text=labeled("stop", "Cancel"), command=app.cancel_task, height=34, width=110,
            **secondary_button_style(),
        )
        self.cancel_button.grid(row=0, column=1, rowspan=2, padx=(12, 0))

        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.grid(row=2, column=0, sticky="ew", pady=(10, 8))
        self.stat_done = StatCard(stats, "Done")
        self.stat_skipped = StatCard(stats, "Skipped")
        self.stat_failed = StatCard(stats, "Failed")
        self.stat_not_run = StatCard(stats, "Not run")
        cards = (self.stat_done, self.stat_skipped, self.stat_failed, self.stat_not_run)
        for column, card in enumerate(cards):
            stats.grid_columnconfigure(column, weight=1, uniform="run_stats")
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0 if column == 3 else 6))

        ctk.CTkLabel(
            self, text="Files that were skipped, failed or not run", font=font(13, "bold"), anchor="w"
        ).grid(row=3, column=0, sticky="w", pady=(2, 4))
        self.table = DataTable(
            self,
            [
                Column("result", "Result", width=90),
                Column("file", "File", width=320),
                Column("message", "Reason", width=420, stretch=True),
            ],
            row_id=lambda row: str(row[3]),
        )
        self.table.grid(row=4, column=0, sticky="nsew")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self.report_button = ctk.CTkButton(
            actions, text=labeled("export", "Save report…"), command=app.save_run_report, height=36,
            **secondary_button_style(),
        )
        self.report_button.grid(row=0, column=0)
        self.csv_button = ctk.CTkButton(
            actions, text=labeled("export", "Export CSV…"), command=self._export_csv, height=36,
            **secondary_button_style(),
        )
        self.csv_button.grid(row=0, column=1, padx=(8, 0))
        self.open_button = ctk.CTkButton(
            actions, text=labeled("open", "Open destination"), command=self._open_destination, height=36,
            **secondary_button_style(),
        )
        self.open_button.grid(row=0, column=2, padx=(8, 0))
        self.undo_button = ctk.CTkButton(
            actions, text=labeled("undo", "Undo this run…"), command=self._undo, height=36,
            **primary_button_style(),
        )
        self.undo_button.grid(row=0, column=3, padx=(8, 0))
        ctk.CTkButton(
            actions, text=labeled("history", "History"), command=lambda: app.show_page("history"),
            height=36, **secondary_button_style(),
        ).grid(row=0, column=4, padx=(8, 0))

    # ----------------------------------------------------------- refreshing

    def refresh(self) -> None:
        app = self.app
        status = app.run_status
        result = app.run_result
        text, kind = run_badge(status, result, app.cancelling)
        self.badge.set(text, kind)

        finished = status is RunStatus.FINISHED and result is not None
        running = status is RunStatus.RUNNING
        self.cancel_button.configure(state="normal" if running and not app.cancelling else "disabled")
        self.report_button.configure(state="normal" if finished else "disabled")
        self.csv_button.configure(state="normal" if finished else "disabled")
        self.open_button.configure(state="normal" if app.run_plan is not None else "disabled")
        self.undo_button.configure(
            state="normal" if finished and result.succeeded and not app.busy else "disabled"
        )

        if finished:
            if self._render_key != id(result):
                self._render_key = id(result)
                rows = problem_rows(result)
                self.table.set_rows([(label, source, message, position) for position, (label, source, message) in enumerate(rows)])
            self.stat_done.set(f"{result.succeeded:,}", format_bytes(result.bytes_done))
            self.stat_skipped.set(f"{result.skipped:,}")
            self.stat_failed.set(f"{result.failed:,}")
            self.stat_not_run.set(f"{result.not_run:,}")
            self.bar.set(1)
            created = f" {plural(len(result.created_dirs), 'folder')} created." if result.created_dirs else ""
            self.progress_label.configure(
                text=f"Run {result.run_id} finished. Details are saved in History.{created}"
            )
        elif running:
            self._render_key = None
            self.table.set_rows([])
            self.refresh_progress()
        else:
            self._render_key = None
            self.table.set_rows([])
            for card in (self.stat_done, self.stat_skipped, self.stat_failed, self.stat_not_run):
                card.set("—")
            self.bar.set(0)
            if status is RunStatus.ERROR:
                self.progress_label.configure(text=f"The operation could not run: {app.run_error}")
            else:
                self.progress_label.configure(
                    text="Nothing has been run in this session. Build a preview and press Run."
                )

    def refresh_progress(self) -> None:
        app = self.app
        progress = app.run_progress
        plan = app.run_plan
        if progress is None:
            self.progress_label.configure(text="Starting…")
            return
        verb = "Moving" if plan is not None and plan.options.action is Action.MOVE else "Copying"
        fraction = progress.completed / progress.total if progress.total else 0.0
        self.bar.set(fraction)
        current = f"\n{shorten_path(str(progress.current), 90)}" if progress.current else ""
        cancelling = " (cancelling after the current file)" if app.cancelling else ""
        self.progress_label.configure(
            text=(
                f"{verb} {progress.completed:,} of {progress.total:,} · "
                f"{format_bytes(progress.bytes_done)} of {format_bytes(progress.bytes_total)}"
                f"{cancelling}{current}"
            )
        )
        self.stat_done.set(f"{progress.succeeded:,}", format_bytes(progress.bytes_done))
        self.stat_skipped.set(f"{progress.skipped:,}")
        self.stat_failed.set(f"{progress.failed:,}")
        self.stat_not_run.set("—")

    # -------------------------------------------------------------- actions

    def _export_csv(self) -> None:
        result = self.app.run_result
        if result is not None:
            self.app.export_run_csv(result.run_id)

    def _open_destination(self) -> None:
        plan = self.app.run_plan
        if plan is not None:
            self.app.open_folder(str(plan.destination))

    def _undo(self) -> None:
        result = self.app.run_result
        if result is None:
            messagebox.showinfo(APP_NAME, "There is no finished run to undo.", parent=self.app)
            return
        self.app.start_undo(result.run_id)