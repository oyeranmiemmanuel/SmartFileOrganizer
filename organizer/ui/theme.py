"""Colours, fonts, symbols and table styling shared by every screen.

Colours are (light, dark) pairs; customtkinter switches between them itself.
Icons are plain Unicode symbols so no image files or extra packages are needed.
"""

from __future__ import annotations

from tkinter import ttk

import customtkinter as ctk

APP_NAME = "Smart File Organizer"

SIDEBAR_BG = ("#e8ebf2", "#16181d")
CARD_BG = ("#ffffff", "#23262d")
CARD_BORDER = ("#d5d9e2", "#33373f")
ACCENT = ("#2f6fd6", "#3b82f6")
ACCENT_HOVER = ("#2559b0", "#2f6fd6")
ON_ACCENT = ("#ffffff", "#ffffff")
NAV_HOVER = ("#d9deea", "#262a33")
TEXT = ("#1c1f26", "#e8eaf0")
MUTED = ("#5b6472", "#9aa3b2")
SUCCESS = ("#1e7a43", "#4cc27a")
WARNING = ("#9a6700", "#e3b341")
DANGER = ("#b3261e", "#f2706b")

# badge kind -> (background, text)
BADGES = {
    "neutral": (("#e3e6ee", "#2f333c"), ("#2b303a", "#d7dbe5")),
    "info": (("#dbe8fd", "#1d3a66"), ("#1d3a66", "#cfe0ff")),
    "success": (("#d9f2e3", "#173d28"), ("#17603a", "#b5ecc9")),
    "warning": (("#fbecc7", "#4a3500"), ("#6b4a00", "#ffe3a0")),
    "danger": (("#fbdcd9", "#4a1511"), ("#8a1c15", "#ffc9c4")),
}

ICONS = {
    "dashboard": "⌂",
    "scan": "↻",
    "find": "◎",
    "preview": "☰",
    "run": "▶",
    "history": "↺",
    "rules": "✎",
    "settings": "⚙",
    "folder": "▤",
    "open": "↗",
    "stop": "■",
    "undo": "↺",
    "export": "⇩",
    "ok": "✓",
    "warning": "⚠",
    "error": "✕",
    "info": "ℹ",
}


def labeled(icon: str, text: str) -> str:
    return f"{ICONS[icon]}  {text}"


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


TREE_STYLE = "SFO.Treeview"

_TREE_COLORS = {
    "Light": {
        "bg": "#ffffff", "fg": "#1c1f26", "heading_bg": "#eef1f6", "heading_fg": "#2b303a",
        "selected_bg": "#cfe0fb", "selected_fg": "#10213f",
    },
    "Dark": {
        "bg": "#23262d", "fg": "#e8eaf0", "heading_bg": "#2c3038", "heading_fg": "#e8eaf0",
        "selected_bg": "#2f4f86", "selected_fg": "#ffffff",
    },
}


def apply_treeview_style(ui_scale: float = 1.0) -> None:
    """(Re)style the table for the current light/dark mode.

    Needs a Tk root to exist. Call again after the appearance mode changes.
    With the "System" mode the table follows the OS theme as of the last call.
    """
    colors = _TREE_COLORS.get(ctk.get_appearance_mode(), _TREE_COLORS["Dark"])
    size = max(9, round(10 * ui_scale))
    style = ttk.Style()
    style.theme_use("default")
    style.configure(
        TREE_STYLE,
        background=colors["bg"],
        foreground=colors["fg"],
        fieldbackground=colors["bg"],
        borderwidth=0,
        rowheight=round(28 * ui_scale),
        font=("Segoe UI", size),
    )
    style.map(
        TREE_STYLE,
        background=[("selected", colors["selected_bg"])],
        foreground=[("selected", colors["selected_fg"])],
    )
    style.configure(
        f"{TREE_STYLE}.Heading",
        background=colors["heading_bg"],
        foreground=colors["heading_fg"],
        relief="flat",
        borderwidth=0,
        padding=(8, 6),
        font=("Segoe UI", size, "bold"),
    )
    style.map(f"{TREE_STYLE}.Heading", background=[("active", colors["heading_bg"])])