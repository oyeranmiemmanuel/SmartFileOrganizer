"""Find Files: search the scan for individual files, tick the ones you want, then preview them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from ..formatting import format_bytes, plural
from ..search import MATCH_MODES, SIZE_UNITS, SearchError, build_criteria, format_mtime
from .theme import DANGER, MUTED, font, labeled
from .widgets import Card, Column, DataTable, Page, primary_button_style, secondary_button_style

if TYPE_CHECKING:
    from ..app import App

MAX_ROWS = 5000
ANY_CATEGORY = "Any category"


def _checkbox(value: Any) -> str:
    return "☑" if value else "☐"


class FindPage(Page):
    def __init__(self, master: Any, app: "App") -> None:
        super().__init__(master, app)
        self._render_key: tuple[Any, ...] | None = None
        self._category_key: tuple[str, ...] | None = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(header, text="Find Files", font=font(26, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(
            header,
            text=(
                "Search the scanned files, tick the matches you want, then preview moving or copying "
                "only those. Nothing is changed on this page."
            ),
            text_color=MUTED, anchor="w", justify="left", wraplength=820,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        criteria = Card(self)
        criteria.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        body = criteria.body
        for column, weight in enumerate((3, 2, 2, 2, 2)):
            body.grid_columnconfigure(column, weight=weight)

        def add(column: int, row: int, label: str, widget: Any, padx: Any = (0, 8)) -> None:
            ctk.CTkLabel(body, text=label, font=font(12), text_color=MUTED, anchor="w").grid(
                row=row, column=column, sticky="w", padx=padx
            )
            widget.grid(row=row + 1, column=column, sticky="ew", padx=padx, pady=(2, 8))

        self.name_entry = ctk.CTkEntry(body, height=34, placeholder_text="e.g. invoice or *.pdf")
        self.match_menu = ctk.CTkOptionMenu(body, values=list(MATCH_MODES), height=34)
        self.min_entry = ctk.CTkEntry(body, height=34, placeholder_text="no minimum")
        self.max_entry = ctk.CTkEntry(body, height=34, placeholder_text="no maximum")
        self.unit_menu = ctk.CTkOptionMenu(body, values=list(SIZE_UNITS), height=34)
        self.unit_menu.set("MB")
        self.types_entry = ctk.CTkEntry(body, height=34, placeholder_text="e.g. jpg, png (none = no extension)")
        self.category_menu = ctk.CTkOptionMenu(body, values=[ANY_CATEGORY], height=34)
        self.from_entry = ctk.CTkEntry(body, height=34, placeholder_text="YYYY-MM-DD")
        self.to_entry = ctk.CTkEntry(body, height=34, placeholder_text="YYYY-MM-DD")
        self.folder_entry = ctk.CTkEntry(body, height=34, placeholder_text="part of a subfolder name")

        add(0, 0, "File name", self.name_entry)
        add(1, 0, "Name match", self.match_menu)
        add(2, 0, "Size from", self.min_entry)
        add(3, 0, "Size to", self.max_entry)
        add(4, 0, "Size unit", self.unit_menu, padx=0)
        add(0, 2, "File types", self.types_entry)
        add(1, 2, "Category", self.category_menu)
        add(2, 2, "Modified from", self.from_entry)
        add(3, 2, "Modified to", self.to_entry)
        add(4, 2, "In subfolder containing", self.folder_entry, padx=0)
        for entry in (
            self.name_entry, self.min_entry, self.max_entry, self.types_entry,
            self.from_entry, self.to_entry, self.folder_entry,
        ):
            entry.bind("<Return>", lambda _event: self._search())

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=4, column=0, columnspan=5, sticky="ew")
        actions.grid_columnconfigure(2, weight=1)
        self.search_button = ctk.CTkButton(
            actions, text=labeled("find", "Search"), command=self._search, height=36, width=120,
            **primary_button_style(),
        )
        self.search_button.grid(row=0, column=0)
        self.clear_button = ctk.CTkButton(
            actions, text="Clear", command=self._clear, height=36, width=90, **secondary_button_style()
        )
        self.clear_button.grid(row=0, column=1, padx=(8, 0))
        self.message = ctk.CTkLabel(actions, text="", anchor="w", text_color=DANGER, font=font(12))
        self.message.grid(row=0, column=2, sticky="ew", padx=(12, 0))

        self.table = DataTable(
            self,
            [
                Column("pick", "Pick", width=60, anchor="center", formatter=_checkbox, searchable=False),
                Column("name", "Name", width=260, stretch=True),
                Column("type", "Type", width=80),
                Column("folder", "Subfolder", width=170),
                Column("size", "Size", width=90, anchor="e", formatter=format_bytes, searchable=False),
                Column("modified", "Modified", width=130),
                Column("category", "Category", width=130),
            ],
            row_id=lambda row: f"f{row[7]}",
            on_click=self._on_cell_click,
            on_space=self._toggle_by_id,
        )
        self.table.grid(row=2, column=0, sticky="nsew")

        self.empty = ctk.CTkFrame(self, fg_color="transparent")
        self.empty.grid_columnconfigure(0, weight=1)
        self.empty_label = ctk.CTkLabel(
            self.empty, text="", text_color=MUTED, font=font(14), justify="center", wraplength=600
        )
        self.empty_label.grid(row=0, column=0, pady=(40, 12))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        self.count_label = ctk.CTkLabel(bottom, text="", anchor="w", font=font(13, "bold"))
        self.count_label.grid(row=0, column=0, sticky="w")
        self.select_all_button = ctk.CTkButton(
            bottom, text="Select all matches", command=self._select_all, height=36, **secondary_button_style()
        )
        self.select_all_button.grid(row=0, column=1, padx=(8, 0))
        self.select_none_button = ctk.CTkButton(
            bottom, text="Select none", command=self._select_none, height=36, **secondary_button_style()
        )
        self.select_none_button.grid(row=0, column=2, padx=(8, 0))
        self.preview_button = ctk.CTkButton(
            bottom, text=labeled("preview", "Preview ticked files"), command=app.use_found_files,
            height=36, **primary_button_style(),
        )
        self.preview_button.grid(row=0, column=3, padx=(8, 0))

        self.footer = ctk.CTkLabel(
            self, text="", text_color=MUTED, anchor="w", justify="left", wraplength=820, font=font(12)
        )
        self.footer.grid(row=4, column=0, sticky="ew", pady=(6, 0))

    # ----------------------------------------------------------- refreshing

    def refresh(self) -> None:
        app = self.app
        has_scan = app.scan is not None
        busy = app.busy

        categories = [ANY_CATEGORY] + list(app.rules.categories)
        key = tuple(categories)
        if key != self._category_key:
            current = self.category_menu.get()
            self.category_menu.configure(values=categories)
            self.category_menu.set(current if current in categories else ANY_CATEGORY)
            self._category_key = key

        form_state = "normal" if has_scan and not busy else "disabled"
        self.search_button.configure(state=form_state)
        self.clear_button.configure(state=form_state)

        results = app.search_results
        if not has_scan:
            self._show_empty("Scan a folder first (Dashboard), then come back to search the results.")
            return
        if app.task_kind == "search":
            self._show_empty("Searching…")
            return
        if results is None:
            self._show_empty("Enter your criteria above and press Search. With nothing entered, every scanned file matches.")
            return
        if not results:
            self._show_empty("No files matched. Try fewer or broader criteria.")
            return

        self.empty.grid_remove()
        self.table.grid(row=2, column=0, sticky="nsew")
        key_now = self._current_key()
        if key_now != self._render_key:
            self._render_key = key_now
            self.table.set_rows([self._row(index, hit) for index, hit in enumerate(results[:MAX_ROWS])])
        self._update_labels()

    def _current_key(self) -> tuple[Any, ...]:
        return (id(self.app.search_results), self.app.found_version)

    def _row(self, index: int, hit: Any) -> tuple[Any, ...]:
        item = hit.file
        return (
            hit.key in self.app.found_ticked,
            item.name,
            item.extension or "(none)",
            "/".join(item.relative_dir) or "(top level)",
            item.size,
            format_mtime(item.mtime_ns),
            hit.category,
            index,
        )

    def _show_empty(self, text: str) -> None:
        self._render_key = None
        self.table.grid_remove()
        self.empty.grid(row=2, column=0, sticky="nsew")
        self.empty_label.configure(text=text)
        self.count_label.configure(text="")
        self.footer.configure(text="")
        for button in (self.select_all_button, self.select_none_button, self.preview_button):
            button.configure(state="disabled")

    def _update_labels(self) -> None:
        app = self.app
        results = app.search_results or []
        ticked = app.found_ticked
        size = sum(hit.file.size for hit in results if hit.key in ticked)
        self.count_label.configure(
            text=f"{plural(len(results), 'match', 'matches')} · {len(ticked):,} ticked ({format_bytes(size)})"
        )
        busy = app.busy
        self.select_all_button.configure(state="normal" if results and not busy else "disabled")
        self.select_none_button.configure(state="normal" if ticked and not busy else "disabled")
        self.preview_button.configure(state="normal" if ticked and not busy else "disabled")
        note = "All matches start ticked. Untick any you want to leave out."
        if len(results) > MAX_ROWS:
            note = (
                f"Showing the first {MAX_ROWS:,} of {len(results):,} matches. Select all and "
                "Select none still apply to every match; narrow the search to review them all."
            )
        self.footer.configure(text=note)

    # -------------------------------------------------------------- actions

    def _search(self) -> None:
        app = self.app
        if app.busy or app.scan is None:
            return
        category = self.category_menu.get()
        try:
            criteria = build_criteria(
                text=self.name_entry.get(),
                match=MATCH_MODES[self.match_menu.get()],
                extensions_text=self.types_entry.get(),
                category=None if category == ANY_CATEGORY else category,
                min_size_text=self.min_entry.get(),
                max_size_text=self.max_entry.get(),
                size_unit=self.unit_menu.get(),
                modified_from_text=self.from_entry.get(),
                modified_to_text=self.to_entry.get(),
                folder_text=self.folder_entry.get(),
            )
        except SearchError as exc:
            self.message.configure(text=str(exc))
            return
        self.message.configure(text="")
        app.start_search(criteria)

    def _clear(self) -> None:
        for entry in (
            self.name_entry, self.min_entry, self.max_entry, self.types_entry,
            self.from_entry, self.to_entry, self.folder_entry,
        ):
            entry.delete(0, "end")
        self.match_menu.set(next(iter(MATCH_MODES)))
        self.unit_menu.set("MB")
        self.category_menu.set(ANY_CATEGORY)
        self.message.configure(text="")
        self.app.clear_search()

    def _on_cell_click(self, row_id: str, column: str) -> None:
        if column == "pick":
            self._toggle_by_id(row_id)

    def _toggle_by_id(self, row_id: str) -> None:
        results = self.app.search_results
        if not results:
            return
        try:
            index = int(row_id[1:])
        except ValueError:
            return
        if not 0 <= index < len(results):
            return
        hit = results[index]
        self.app.toggle_found(hit.key)
        self.table.update_row(self._row(index, hit))
        self._render_key = self._current_key()
        self._update_labels()

    def _select_all(self) -> None:
        results = self.app.search_results or []
        self.app.set_found_ticked(hit.key for hit in results)

    def _select_none(self) -> None:
        self.app.set_found_ticked([])