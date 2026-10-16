"""A small modal form used to ask for a folder name or a keyword."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import customtkinter as ctk

from .theme import DANGER, MUTED, font
from .widgets import primary_button_style, secondary_button_style


@dataclass(frozen=True)
class FormField:
    key: str
    label: str
    initial: str = ""
    choices: tuple[str, ...] = ()  # when given, the field is an editable drop-down list


class FormDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master: Any,
        title: str,
        fields: Sequence[FormField],
        description: str,
        ok_text: str,
        validate: Callable[[dict[str, str]], str | None] | None,
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.result: dict[str, str] | None = None
        self._validate = validate
        self._widgets: dict[str, Any] = {}
        self._grab_attempts = 0
        self.grid_columnconfigure(0, weight=1)

        row = 0
        if description:
            ctk.CTkLabel(
                self, text=description, text_color=MUTED, anchor="w", justify="left",
                wraplength=460, font=font(12),
            ).grid(row=row, column=0, sticky="ew", padx=20, pady=(18, 6))
            row += 1
        for field in fields:
            ctk.CTkLabel(self, text=field.label, font=font(13, "bold"), anchor="w").grid(
                row=row, column=0, sticky="w", padx=20, pady=(10, 2)
            )
            row += 1
            if field.choices:
                widget: Any = ctk.CTkComboBox(self, values=list(field.choices), width=460, height=36)
                widget.set(field.initial)
            else:
                widget = ctk.CTkEntry(self, width=460, height=36)
                widget.insert(0, field.initial)
            widget.grid(row=row, column=0, sticky="ew", padx=20)
            row += 1
            self._widgets[field.key] = widget

        self.error = ctk.CTkLabel(
            self, text="", text_color=DANGER, anchor="w", justify="left", wraplength=460, font=font(12)
        )
        self.error.grid(row=row, column=0, sticky="ew", padx=20, pady=(8, 0))
        row += 1
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=row, column=0, sticky="e", padx=20, pady=(12, 18))
        ctk.CTkButton(buttons, text="Cancel", width=100, command=self.destroy, **secondary_button_style()).grid(
            row=0, column=0
        )
        ctk.CTkButton(buttons, text=ok_text, width=100, command=self._ok, **primary_button_style()).grid(
            row=0, column=1, padx=(8, 0)
        )
        self.bind("<Return>", lambda _event: self._ok())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.after(150, self._prepare)

    def _prepare(self) -> None:
        try:
            self.lift()
            self.grab_set()
        except tk.TclError:  # the window is not visible yet
            self._grab_attempts += 1
            if self._grab_attempts < 10:
                self.after(100, self._prepare)
            return
        first = next(iter(self._widgets.values()), None)
        if first is not None:
            try:
                first.focus_set()
            except Exception:
                pass

    def _ok(self) -> None:
        values = {key: widget.get().strip() for key, widget in self._widgets.items()}
        if self._validate is not None:
            message = self._validate(values)
            if message:
                self.error.configure(text=message)
                return
        self.result = values
        self.destroy()


def ask_form(
    master: Any,
    title: str,
    fields: Sequence[FormField],
    *,
    description: str = "",
    ok_text: str = "Save",
    validate: Callable[[dict[str, str]], str | None] | None = None,
) -> dict[str, str] | None:
    """Show the form and wait. Returns the entered values, or None if cancelled."""
    dialog = FormDialog(master, title, fields, description, ok_text, validate)
    master.wait_window(dialog)
    return dialog.result