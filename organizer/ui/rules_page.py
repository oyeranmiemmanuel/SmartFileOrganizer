"""Rules: destination folder names, filename keyword rules and your extension changes."""

from __future__ import annotations

from collections import Counter
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from ..formatting import format_count
from .theme import APP_NAME, MUTED, font, labeled
from .widgets import (
    Card,
    Column,
    DataTable,
    MessageList,
    Page,
    primary_button_style,
    secondary_button_style,
)

if TYPE_CHECKING:
    from ..app import App


class RulesPage(Page):
    def __init__(self, master: Any, app: "App") -> None:
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(header, text="Rules", font=font(26, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text=(
                "Change where files go. To send one file type somewhere else, double-click it on the "
                "Scan Results page. Changes are saved to your rules file and apply to the next preview."
            ),
            text_color=MUTED, anchor="w", justify="left", wraplength=820,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        self.banner = MessageList(body)
        self.banner.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        # Destination folders
        folders = Card(body, "Destination folders by category")
        folders.grid(row=1, column=0, sticky="ew")
        self.folder_table = DataTable(
            folders.body,
            [
                Column("category", "Category", width=200),
                Column("folder", "Destination folder", width=240, stretch=True),
                Column("count", "Extensions", width=90, anchor="e", formatter=format_count, searchable=False),
            ],
            row_id=lambda row: str(row[0]),
            height=8,
        )
        self.folder_table.grid(row=0, column=0, sticky="ew")
        row = ctk.CTkFrame(folders.body, fg_color="transparent")
        row.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.rename_button = ctk.CTkButton(
            row, text=labeled("rules", "Rename folder…"), command=self._rename, height=34, **primary_button_style()
        )
        self.rename_button.grid(row=0, column=0)
        self.reset_folder_button = ctk.CTkButton(
            row, text="Reset folder name", command=self._reset_folder, height=34, **secondary_button_style()
        )
        self.reset_folder_button.grid(row=0, column=1, padx=(8, 0))

        # Keyword rules
        keywords = Card(body, "Filename keyword rules")
        keywords.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        ctk.CTkLabel(
            keywords.body,
            text="Files whose NAME contains the keyword go to that folder, before extension rules apply.",
            text_color=MUTED, anchor="w", font=font(12),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.keyword_table = DataTable(
            keywords.body,
            [Column("keyword", "Keyword", width=220), Column("folder", "Folder", width=260, stretch=True)],
            row_id=lambda row: f"k{row[2]}",
            height=4,
        )
        self.keyword_table.grid(row=1, column=0, sticky="ew")
        row = ctk.CTkFrame(keywords.body, fg_color="transparent")
        row.grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.add_keyword_button = ctk.CTkButton(
            row, text="Add keyword rule…", command=app.add_keyword_rule, height=34, **primary_button_style()
        )
        self.add_keyword_button.grid(row=0, column=0)
        self.remove_keyword_button = ctk.CTkButton(
            row, text="Remove selected", command=self._remove_keyword, height=34, **secondary_button_style()
        )
        self.remove_keyword_button.grid(row=0, column=1, padx=(8, 0))

        # Extension changes
        changes = Card(body, "Your file type changes")
        changes.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        self.change_table = DataTable(
            changes.body,
            [Column("extension", "File type", width=160), Column("category", "Sent to category", width=260, stretch=True)],
            row_id=lambda row: f"o{row[0]}",
            height=4,
        )
        self.change_table.grid(row=0, column=0, sticky="ew")
        row = ctk.CTkFrame(changes.body, fg_color="transparent")
        row.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.remove_change_button = ctk.CTkButton(
            row, text="Remove selected change", command=self._remove_change, height=34, **secondary_button_style()
        )
        self.remove_change_button.grid(row=0, column=0)

        # Rules file
        file_card = Card(body, "Rules file")
        file_card.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        row = ctk.CTkFrame(file_card.body, fg_color="transparent")
        row.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            row, text=labeled("open", "Open rules file"), command=app.open_rules_file, height=34,
            **secondary_button_style(),
        ).grid(row=0, column=0)
        ctk.CTkButton(
            row, text=labeled("scan", "Reload"), command=app.reload_rules, height=34, **secondary_button_style()
        ).grid(row=0, column=1, padx=(8, 0))
        self.reset_all_button = ctk.CTkButton(
            row, text="Reset all my changes…", command=app.reset_all_rules, height=34, **secondary_button_style()
        )
        self.reset_all_button.grid(row=0, column=2, padx=(8, 0))

    # ----------------------------------------------------------- refreshing

    def refresh(self) -> None:
        app = self.app
        rules = app.rules
        messages: list[tuple[str, str]] = []
        if app.rules_error:
            messages.append(
                ("error", f"{app.rules_error} Editing is locked so your file is not overwritten. "
                          "Fix it with Open rules file and press Reload, or use Reset all my changes.")
            )
        for warning in app.rules_warnings[:4]:
            messages.append(("warning", warning))
        self.banner.set(messages)

        counts = Counter(rules.extension_map.values())
        self.folder_table.set_rows(
            [(category, rules.folder_for(category), counts.get(category, 0)) for category in rules.categories]
        )
        self.keyword_table.set_rows(
            [(rule.keyword, rule.folder, position) for position, rule in enumerate(rules.keyword_rules)]
        )
        overrides = app.rules_overlay.get("extension_overrides")
        change_rows = (
            [(str(ext), str(cat)) for ext, cat in overrides.items()] if isinstance(overrides, dict) else []
        )
        self.change_table.set_rows(change_rows)

        editable = "normal" if app.rules_editable and not app.busy else "disabled"
        for button in (
            self.rename_button, self.reset_folder_button, self.add_keyword_button,
            self.remove_keyword_button, self.remove_change_button,
        ):
            button.configure(state=editable)
        self.reset_all_button.configure(state="disabled" if app.busy else "normal")

    # -------------------------------------------------------------- actions

    def _rename(self) -> None:
        category = self.folder_table.selected_id()
        if category is None:
            messagebox.showinfo(APP_NAME, "Select a category first.", parent=self.app)
            return
        self.app.rename_category_folder(category)

    def _reset_folder(self) -> None:
        category = self.folder_table.selected_id()
        if category is None:
            messagebox.showinfo(APP_NAME, "Select a category first.", parent=self.app)
            return
        self.app.reset_category_folder(category)

    def _remove_keyword(self) -> None:
        row_id = self.keyword_table.selected_id()
        row = self.keyword_table.get_row(row_id) if row_id else None
        if row is None:
            messagebox.showinfo(APP_NAME, "Select a keyword rule first.", parent=self.app)
            return
        self.app.remove_keyword_rule(str(row[0]))

    def _remove_change(self) -> None:
        row_id = self.change_table.selected_id()
        row = self.change_table.get_row(row_id) if row_id else None
        if row is None:
            messagebox.showinfo(APP_NAME, "Select a change first.", parent=self.app)
            return
        self.app.remove_extension_override(str(row[0]))