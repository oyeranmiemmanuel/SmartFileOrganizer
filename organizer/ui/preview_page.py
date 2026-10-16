"""Preview: the complete plan, with options and filters, before anything is changed."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from ..formatting import format_bytes, plural
from ..plan_filters import STATUS_OPTIONS, filter_items, plan_categories, plan_extensions
from ..planner import Action
from .operation_state import (
    ACTION_CHOICES,
    CONFLICT_CHOICES,
    LAYOUT_CHOICES,
    PlanStatus,
    plan_badge,
    preview_row,
)
from .theme import MUTED, font, labeled
from .widgets import (
    Column,
    DataTable,
    Page,
    StatusBadge,
    primary_button_style,
    secondary_button_style,
)
from ..formatting import format_count

if TYPE_CHECKING:
    from ..app import App

ALL_CATEGORIES = "All categories"
ALL_TYPES = "All types"


def _type_label(extension: str) -> str:
    return extension or "(no extension)"


class PreviewPage(Page):
    def __init__(self, master: Any, app: "App") -> None:
        super().__init__(master, app)
        self._render_key: int | None = None
        self._ext_by_label: dict[str, str] = {}
        self._filter_after: str | None = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Preview", font=font(26, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        self.badge = StatusBadge(header)
        self.badge.grid(row=0, column=1, sticky="e")
        self.summary = ctk.CTkLabel(
            header, text="", text_color=MUTED, anchor="w", justify="left", wraplength=820
        )
        self.summary.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        options.grid_columnconfigure(3, weight=1)
        self.action_button = ctk.CTkSegmentedButton(
            options, values=list(ACTION_CHOICES), command=lambda value: app.set_plan_option("action", value)
        )
        self.action_button.grid(row=0, column=0)
        self.conflict_menu = ctk.CTkOptionMenu(
            options, values=list(CONFLICT_CHOICES), width=210,
            command=lambda value: app.set_plan_option("conflict", value),
        )
        self.conflict_menu.grid(row=0, column=1, padx=(8, 0))
        self.layout_menu = ctk.CTkOptionMenu(
            options, values=list(LAYOUT_CHOICES), width=230,
            command=lambda value: app.set_plan_option("layout", value),
        )
        self.layout_menu.grid(row=0, column=2, padx=(8, 0))
        self.refresh_button = ctk.CTkButton(
            options, text=labeled("scan", "Refresh"), command=app.refresh_preview, height=32, width=100,
            **secondary_button_style(),
        )
        self.refresh_button.grid(row=0, column=4, padx=(8, 0))
        self.run_button = ctk.CTkButton(
            options, text=labeled("run", "Run…"), command=app.request_run, height=32,
            font=font(13, "bold"), **primary_button_style(),
        )
        self.run_button.grid(row=0, column=5, padx=(8, 0))

        filters = ctk.CTkFrame(self, fg_color="transparent")
        filters.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        filters.grid_columnconfigure(0, weight=1)
        self.search = ctk.CTkEntry(filters, placeholder_text="Search file names, folders or notes…", height=34)
        self.search.grid(row=0, column=0, sticky="ew")
        self.search.bind("<KeyRelease>", self._schedule_filter)
        self.status_menu = ctk.CTkOptionMenu(
            filters, values=list(STATUS_OPTIONS), width=120, command=self._apply_filters
        )
        self.status_menu.grid(row=0, column=1, padx=(8, 0))
        self.category_menu = ctk.CTkOptionMenu(
            filters, values=[ALL_CATEGORIES], width=170, command=self._apply_filters
        )
        self.category_menu.grid(row=0, column=2, padx=(8, 0))
        self.extension_menu = ctk.CTkOptionMenu(
            filters, values=[ALL_TYPES], width=130, command=self._apply_filters
        )
        self.extension_menu.grid(row=0, column=3, padx=(8, 0))

        self.table = DataTable(
            self,
            [
                Column("status", "Status", width=90),
                Column("file", "File", width=250),
                Column("goes_to", "Goes to", width=300, stretch=True),
                Column("category", "Category", width=130),
                Column("size", "Size", width=90, anchor="e", formatter=format_bytes, searchable=False),
                Column("note", "Note", width=260),
            ],
            row_id=lambda row: str(row[6]),
        )
        self.table.grid(row=3, column=0, sticky="nsew")

        self.empty = ctk.CTkFrame(self, fg_color="transparent")
        self.empty.grid_columnconfigure(0, weight=1)
        self.empty_label = ctk.CTkLabel(
            self.empty, text="", text_color=MUTED, font=font(14), justify="center", wraplength=600
        )
        self.empty_label.grid(row=0, column=0, pady=(60, 12))

        self.footer = ctk.CTkLabel(
            self, text="", text_color=MUTED, anchor="w", justify="left", wraplength=820, font=font(12)
        )
        self.footer.grid(row=4, column=0, sticky="ew", pady=(6, 0))

    # ----------------------------------------------------------- refreshing

    def refresh(self) -> None:
        app = self.app
        plan = app.plan
        busy = app.busy
        text, kind = plan_badge(app.plan_status)
        self.badge.set(text, kind)

        self.action_button.set(app.action_label)
        self.conflict_menu.set(app.conflict_label)
        self.layout_menu.set(app.layout_label)
        recursive = app.scan.recursive if app.scan is not None else False
        enabled = "disabled" if busy else "normal"
        self.action_button.configure(state=enabled)
        self.conflict_menu.configure(state=enabled)
        self.layout_menu.configure(state="normal" if recursive and not busy else "disabled")
        self.refresh_button.configure(state="normal" if app.scan is not None and not busy else "disabled")

        if plan is None:
            self._show_empty()
            return
        self.empty.grid_remove()
        self.table.grid(row=3, column=0, sticky="nsew")

        if self._render_key != id(plan):
            self._render_key = id(plan)
            self._update_menus(plan)
            self._apply_filters()

        summary = plan.summary()
        verb = "move" if plan.options.action is Action.MOVE else "copy"
        count = summary.ready + summary.renamed
        self.summary.configure(
            text=(
                f"Will {verb} {plural(count, 'file')} ({format_bytes(summary.executable_bytes)}) · "
                f"{summary.renamed:,} renamed · {summary.skipped:,} skipped · {summary.blocked:,} blocked"
            )
        )
        self.run_button.configure(
            text=labeled("run", f"{verb.capitalize()} {plural(count, 'file')}…"),
            state="normal" if count and not busy else "disabled",
        )
        self._update_footer(plan)

    def _show_empty(self) -> None:
        app = self.app
        self._render_key = None
        self.table.grid_remove()
        self.empty.grid(row=3, column=0, sticky="nsew")
        self.run_button.configure(text=labeled("run", "Run…"), state="disabled")
        self.summary.configure(text="")
        self.footer.configure(text="")
        if app.scan is None:
            text = "Scan a folder first, then choose the file types on the Scan Results page."
        elif app.plan_status is PlanStatus.BUILDING:
            text = "Building the preview…"
        elif app.plan_status is PlanStatus.ERROR:
            text = f"The preview could not be built.\n{app.plan_error}"
        elif not app.has_selection:
            text = "No file types are selected. Choose at least one on the Scan Results page."
        elif app.plan_note:
            text = app.plan_note + "\nPress Refresh to build the preview again."
        else:
            text = "Press Refresh to build the preview."
        self.empty_label.configure(text=text)

    def _update_menus(self, plan: Any) -> None:
        categories = [ALL_CATEGORIES] + plan_categories(plan)
        current = self.category_menu.get()
        self.category_menu.configure(values=categories)
        self.category_menu.set(current if current in categories else ALL_CATEGORIES)

        extensions = plan_extensions(plan)
        self._ext_by_label = {_type_label(ext): ext for ext in extensions}
        labels = [ALL_TYPES] + [_type_label(ext) for ext in extensions]
        current = self.extension_menu.get()
        self.extension_menu.configure(values=labels)
        self.extension_menu.set(current if current in labels else ALL_TYPES)

    def _update_footer(self, plan: Any) -> None:
        parts: list[str] = []
        if self.app.selection_mode == "files":
            parts.append("Only the individual files chosen on Find Files are included.")
        for warning in plan.warnings:
            parts.append(f"⚠ {warning}")
        shown = self.table.visible_count
        parts.append(f"Showing {shown:,} of {len(plan.items):,} files. Nothing has been changed yet.")
        self.footer.configure(text="\n".join(parts))

    # -------------------------------------------------------------- filters

    def _schedule_filter(self, _event: Any = None) -> None:
        if self._filter_after is not None:
            self.after_cancel(self._filter_after)
        self._filter_after = self.after(200, self._apply_filters)

    def _apply_filters(self, _value: Any = None) -> None:
        self._filter_after = None
        plan = self.app.plan
        if plan is None:
            return
        category_label = self.category_menu.get()
        extension_label = self.extension_menu.get()
        items = filter_items(
            plan.items,
            text=self.search.get(),
            status=self.status_menu.get(),
            category=None if category_label == ALL_CATEGORIES else category_label,
            extension=None if extension_label == ALL_TYPES else self._ext_by_label.get(extension_label),
        )
        self.table.set_rows([preview_row(item, plan) for item in items])
        self._update_footer(plan)