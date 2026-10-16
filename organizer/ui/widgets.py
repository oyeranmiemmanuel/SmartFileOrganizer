"""Reusable building blocks for the screens."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any, Callable, Sequence

import customtkinter as ctk

from .theme import (
    ACCENT,
    ACCENT_HOVER,
    BADGES,
    CARD_BG,
    CARD_BORDER,
    DANGER,
    ICONS,
    MUTED,
    NAV_HOVER,
    ON_ACCENT,
    SUCCESS,
    TEXT,
    TREE_STYLE,
    WARNING,
    font,
    labeled,
)


def primary_button_style() -> dict[str, Any]:
    return {"fg_color": ACCENT, "hover_color": ACCENT_HOVER, "text_color": ON_ACCENT}


def secondary_button_style() -> dict[str, Any]:
    return {
        "fg_color": "transparent",
        "border_width": 1,
        "border_color": CARD_BORDER,
        "text_color": TEXT,
        "hover_color": NAV_HOVER,
    }


class Page(ctk.CTkFrame):
    """Base class for the screens shown in the main area."""

    def __init__(self, master: Any, app: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app

    def refresh(self) -> None:
        """Redraw from the application state."""


class Card(ctk.CTkFrame):
    """A titled panel. Put content in ``card.body``."""

    def __init__(self, master: Any, title: str | None = None) -> None:
        super().__init__(
            master, fg_color=CARD_BG, border_width=1, border_color=CARD_BORDER, corner_radius=12
        )
        self.grid_columnconfigure(0, weight=1)
        if title:
            ctk.CTkLabel(self, text=title, font=font(15, "bold"), anchor="w").grid(
                row=0, column=0, sticky="ew", padx=18, pady=(14, 2)
            )
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=18, pady=(6, 16))
        self.body.grid_columnconfigure(0, weight=1)


class StatCard(ctk.CTkFrame):
    def __init__(self, master: Any, title: str) -> None:
        super().__init__(
            master, fg_color=CARD_BG, border_width=1, border_color=CARD_BORDER, corner_radius=12
        )
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=title, font=font(12), text_color=MUTED, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=16, pady=(12, 0)
        )
        self._value = ctk.CTkLabel(self, text="—", font=font(24, "bold"), anchor="w")
        self._value.grid(row=1, column=0, sticky="ew", padx=16)
        self._hint = ctk.CTkLabel(self, text="", font=font(11), text_color=MUTED, anchor="w")
        self._hint.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))

    def set(self, value: str, hint: str = "") -> None:
        self._value.configure(text=value)
        self._hint.configure(text=hint)


class StatusBadge(ctk.CTkLabel):
    def __init__(self, master: Any, text: str = "", kind: str = "neutral") -> None:
        super().__init__(master, text="", corner_radius=10, height=26, font=font(12, "bold"))
        self.set(text, kind)

    def set(self, text: str, kind: str = "neutral") -> None:
        background, foreground = BADGES.get(kind, BADGES["neutral"])
        self.configure(text=f"  {text}  ", fg_color=background, text_color=foreground)


class MessageList(ctk.CTkFrame):
    """Lines of text coloured by kind: error, warning, ok, info or muted."""

    _COLORS = {"error": DANGER, "warning": WARNING, "ok": SUCCESS, "info": TEXT, "muted": MUTED}
    _ICONS = {"error": ICONS["error"], "warning": ICONS["warning"], "ok": ICONS["ok"], "info": ICONS["info"]}

    def __init__(self, master: Any) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self._labels: list[ctk.CTkLabel] = []
        self._wrap = 600
        self.bind("<Configure>", self._on_resize)

    def set(self, messages: Sequence[tuple[str, str]]) -> None:
        for label in self._labels:
            label.destroy()
        self._labels = []
        for row, (kind, text) in enumerate(messages):
            icon = self._ICONS.get(kind)
            label = ctk.CTkLabel(
                self,
                text=f"{icon}  {text}" if icon else text,
                text_color=self._COLORS.get(kind, TEXT),
                anchor="w",
                justify="left",
                wraplength=self._wrap,
                font=font(12),
            )
            label.grid(row=row, column=0, sticky="ew", pady=1)
            self._labels.append(label)

    def _on_resize(self, event: tk.Event) -> None:
        self._wrap = max(200, event.width - 24)
        for label in self._labels:
            label.configure(wraplength=self._wrap)


class PathField(ctk.CTkFrame):
    """A labelled folder path: text box, Browse button and optional extra buttons."""

    def __init__(
        self,
        master: Any,
        label: str,
        variable: tk.StringVar,
        browse: Callable[[], None],
        extras: Sequence[tuple[str, Callable[[], None]]] = (),
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=label, font=font(13, "bold"), anchor="w").grid(
            row=0, column=0, columnspan=2 + len(extras), sticky="w", pady=(0, 4)
        )
        self.entry = ctk.CTkEntry(self, textvariable=variable, height=36)
        self.entry.grid(row=1, column=0, sticky="ew")
        self._buttons: list[ctk.CTkButton] = []
        actions = [(labeled("folder", "Browse…"), browse, True), *[(t, c, False) for t, c in extras]]
        for column, (text, command, primary) in enumerate(actions, start=1):
            style = primary_button_style() if primary else secondary_button_style()
            button = ctk.CTkButton(self, text=text, command=command, height=36, width=100, **style)
            button.grid(row=1, column=column, padx=(8, 0))
            self._buttons.append(button)

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.entry.configure(state=state)
        for button in self._buttons:
            button.configure(state=state)


@dataclass(frozen=True)
class Column:
    key: str
    heading: str
    width: int = 120
    anchor: str = "w"
    formatter: Callable[[Any], str] = str
    searchable: bool = True
    stretch: bool = False


def _sort_value(value: Any) -> Any:
    return value.casefold() if isinstance(value, str) else value


class DataTable(ctk.CTkFrame):
    """A sortable, filterable table. Rows hold raw values; formatters make the text.

    * A row may hold more values than there are columns; the extra values are
      hidden (for example an id).
    * ``row_id`` turns a row into a unique, non-empty text id. It is required for
      the click callbacks, ``update_row``, ``selected_id`` and ``get_row``.
    * ``on_click(row_id, column_key)`` fires on a click on a cell,
      ``on_double_click`` on a double click, ``on_space(row_id)`` on the space key.

    Call ``apply_treeview_style`` once (a Tk root must exist) before creating one.
    """

    def __init__(
        self,
        master: Any,
        columns: Sequence[Column],
        *,
        row_id: Callable[[tuple], str] | None = None,
        height: int = 10,
        on_click: Callable[[str, str], None] | None = None,
        on_double_click: Callable[[str, str], None] | None = None,
        on_space: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(
            master, fg_color=CARD_BG, border_width=1, border_color=CARD_BORDER, corner_radius=12
        )
        self._columns = list(columns)
        self._row_id = row_id
        self._on_click = on_click
        self._on_double_click = on_double_click
        self._on_space = on_space
        self._rows: list[tuple[Any, ...]] = []
        self._filter = ""
        self._sort_index: int | None = None
        self._sort_desc = False
        self.visible_count = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            self,
            columns=[column.key for column in self._columns],
            show="headings",
            style=TREE_STYLE,
            selectmode="browse",
            height=height,
        )
        scrollbar = ctk.CTkScrollbar(self, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=8)
        for index, column in enumerate(self._columns):
            self.tree.column(
                column.key, width=column.width, minwidth=50, anchor=column.anchor, stretch=column.stretch
            )
            self.tree.heading(
                column.key, text=column.heading, anchor=column.anchor,
                command=lambda i=index: self._sort_by(i),
            )
        self.tree.bind("<Button-1>", self._handle_click, add="+")
        self.tree.bind("<Double-1>", self._handle_double_click, add="+")
        self.tree.bind("<space>", self._handle_space)

    # ------------------------------------------------------------- queries

    @property
    def row_count(self) -> int:
        return len(self._rows)

    def selected_id(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def visible_ids(self) -> list[str]:
        return list(self.tree.get_children())

    def get_row(self, row_id: str) -> tuple[Any, ...] | None:
        if self._row_id is None:
            return None
        for row in self._rows:
            if self._row_id(row) == row_id:
                return row
        return None

    def select(self, row_id: str) -> None:
        if self.tree.exists(row_id):
            self.tree.selection_set(row_id)
            self.tree.see(row_id)

    # ------------------------------------------------------------- changes

    def set_rows(self, rows: Sequence[Sequence[Any]]) -> None:
        self._rows = [tuple(row) for row in rows]
        self._render()

    def set_filter(self, text: str) -> None:
        self._filter = text.strip().casefold()
        self._render()

    def update_row(self, row: Sequence[Any]) -> None:
        """Replace one row's values in place (keeps selection and scroll position)."""
        if self._row_id is None:
            return
        new = tuple(row)
        row_id = self._row_id(new)
        for position, existing in enumerate(self._rows):
            if self._row_id(existing) == row_id:
                self._rows[position] = new
                break
        if self.tree.exists(row_id):
            self.tree.item(row_id, values=self._display(new))

    # ----------------------------------------------------------- internals

    def _display(self, row: tuple[Any, ...]) -> list[str]:
        return [column.formatter(value) for column, value in zip(self._columns, row)]

    def _sort_by(self, index: int) -> None:
        if self._sort_index == index:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_index, self._sort_desc = index, False
        self._render()

    def _render(self) -> None:
        rows = self._rows
        if self._filter:
            needle = self._filter
            rows = [
                row for row in rows
                if any(
                    needle in str(value).casefold()
                    for column, value in zip(self._columns, row)
                    if column.searchable
                )
            ]
        if self._sort_index is not None:
            index = self._sort_index
            rows = sorted(rows, key=lambda row: _sort_value(row[index]), reverse=self._sort_desc)

        selected = self.tree.selection()
        top = self.tree.yview()[0]
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            options: dict[str, Any] = {"values": self._display(row)}
            if self._row_id is not None:
                options["iid"] = self._row_id(row)
            self.tree.insert("", "end", **options)
        for row_id in selected:
            if self.tree.exists(row_id):
                self.tree.selection_set(row_id)
        self.tree.yview_moveto(top)

        self.visible_count = len(rows)
        for index, column in enumerate(self._columns):
            marker = ""
            if index == self._sort_index:
                marker = " ▼" if self._sort_desc else " ▲"
            self.tree.heading(column.key, text=column.heading + marker)

    def _cell_at(self, event: tk.Event) -> tuple[str, str] | None:
        if self.tree.identify_region(event.x, event.y) != "cell":
            return None
        row_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not row_id or not column:
            return None
        try:
            index = int(column.lstrip("#")) - 1
        except ValueError:
            return None
        if not 0 <= index < len(self._columns):
            return None
        return row_id, self._columns[index].key

    def _handle_click(self, event: tk.Event) -> None:
        if self._on_click is None:
            return
        cell = self._cell_at(event)
        if cell is not None:
            self._on_click(*cell)

    def _handle_double_click(self, event: tk.Event) -> None:
        if self._on_double_click is None:
            return
        cell = self._cell_at(event)
        if cell is not None:
            self._on_double_click(*cell)

    def _handle_space(self, _event: tk.Event) -> str:
        row_id = self.selected_id()
        if row_id is not None and self._on_space is not None:
            self._on_space(row_id)
        return "break"


class TextDialog(ctk.CTkToplevel):
    """A simple window showing read-only text (reports, details, skipped files)."""

    def __init__(self, master: Any, title: str, text: str) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry("760x500")
        self.minsize(480, 300)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        box = ctk.CTkTextbox(self, wrap="word", font=font(12))
        box.grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 8))
        box.insert("1.0", text)
        box.configure(state="disabled")
        ctk.CTkButton(self, text="Close", width=100, command=self.destroy, **primary_button_style()).grid(
            row=1, column=0, sticky="e", padx=16, pady=(0, 16)
        )
        self.after(120, self._bring_to_front)

    def _bring_to_front(self) -> None:
        try:
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass