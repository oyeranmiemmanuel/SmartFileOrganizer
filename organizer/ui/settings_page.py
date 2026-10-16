"""Settings: appearance, interface size, classification rules and data locations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from ..history import default_history_dir
from ..settings import (
    APPEARANCE_MODES,
    UI_SCALES,
    app_data_dir,
    default_rules_path,
    default_settings_path,
)
from .theme import MUTED, font, labeled
from .widgets import Card, MessageList, Page, secondary_button_style

if TYPE_CHECKING:
    from ..app import App


class SettingsPage(Page):
    def __init__(self, master: Any, app: "App") -> None:
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text="Settings", font=font(26, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w", pady=(0, 12)
        )
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        # Appearance
        card = Card(body, "Appearance")
        card.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(card.body, text="Theme", font=font(13, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        self.appearance = ctk.CTkSegmentedButton(
            card.body, values=list(APPEARANCE_MODES), command=app.apply_appearance
        )
        self.appearance.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ctk.CTkLabel(card.body, text="Interface size", font=font(13, "bold"), anchor="w").grid(
            row=2, column=0, sticky="w", pady=(16, 0)
        )
        self.scale_menu = ctk.CTkOptionMenu(
            card.body, values=[f"{value}%" for value in UI_SCALES], command=self._on_scale, width=120
        )
        self.scale_menu.grid(row=3, column=0, sticky="w", pady=(6, 0))
        ctk.CTkLabel(
            card.body, text="A new interface size is applied the next time you start the app.",
            text_color=MUTED, anchor="w", font=font(12),
        ).grid(row=4, column=0, sticky="w", pady=(6, 0))

        # Rules
        rules = Card(body, "Classification rules")
        rules.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        ctk.CTkLabel(
            rules.body,
            text=(
                "Classifications are kept in a small JSON file that you can edit without touching the "
                "program. It only needs to list what you want to change: extension overrides, "
                "renamed destination folders and filename keyword rules."
            ),
            text_color=MUTED, anchor="w", justify="left", wraplength=700, font=font(12),
        ).grid(row=0, column=0, sticky="w")
        self.rules_messages = MessageList(rules.body)
        self.rules_messages.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        buttons = ctk.CTkFrame(rules.body, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="w", pady=(12, 0))
        ctk.CTkButton(
            buttons, text=labeled("open", "Open rules file"), command=app.open_rules_file, height=36,
            **secondary_button_style(),
        ).grid(row=0, column=0)
        ctk.CTkButton(
            buttons, text=labeled("scan", "Reload rules"), command=app.reload_rules, height=36,
            **secondary_button_style(),
        ).grid(row=0, column=1, padx=(8, 0))

        # Data locations
        data = Card(body, "Where the app keeps its data")
        data.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self.locations = ctk.CTkLabel(
            data.body, text="", anchor="w", justify="left", wraplength=700, font=font(12)
        )
        self.locations.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            data.body, text=labeled("open", "Open data folder"),
            command=lambda: app.open_folder(str(app_data_dir())), height=36, **secondary_button_style(),
        ).grid(row=1, column=0, sticky="w", pady=(12, 0))

    def refresh(self) -> None:
        app = self.app
        self.appearance.set(app.settings.appearance)
        self.scale_menu.set(f"{app.settings.ui_scale}%")

        messages: list[tuple[str, str]] = [("ok", f"Using {app.rules_origin}.")]
        if app.rules_error:
            messages = [("error", f"{app.rules_error} The built-in rules are being used instead.")]
        messages += [("warning", warning) for warning in app.rules_warnings[:6]]
        if len(app.rules_warnings) > 6:
            messages.append(("muted", f"... and {len(app.rules_warnings) - 6} more warnings."))
        self.rules_messages.set(messages)

        log = str(app.log_path) if app.log_path else "(not available)"
        self.locations.configure(
            text=(
                f"Settings:  {default_settings_path()}\n"
                f"Rules:  {default_rules_path()}\n"
                f"History:  {default_history_dir()}\n"
                f"Log:  {log}"
            )
        )

    def _on_scale(self, value: str) -> None:
        self.app.set_ui_scale(int(value.rstrip("%")))