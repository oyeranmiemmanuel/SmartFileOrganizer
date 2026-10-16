"""Small, pure text helpers used by the user interface."""

from __future__ import annotations

_UNITS = ("KB", "MB", "GB", "TB")


def format_bytes(size: int) -> str:
    """1536 -> '1.5 KB'. Uses 1024-based units, like Windows Explorer."""
    if size < 0:
        size = 0
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in _UNITS:
        value /= 1024
        if value < 1024 or unit == _UNITS[-1]:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} {_UNITS[-1]}"


def format_count(number: int) -> str:
    return f"{number:,}"


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """plural(1, 'file') -> '1 file'; plural(1234, 'file') -> '1,234 files'."""
    word = singular if count == 1 else (plural_form or singular + "s")
    return f"{count:,} {word}"


def shorten_path(path: str, max_length: int = 60) -> str:
    """Shorten a long path with an ellipsis in the middle."""
    if max_length < 5 or len(path) <= max_length:
        return path
    head = (max_length - 1) // 3
    tail = max_length - 1 - head
    return f"{path[:head]}…{path[-tail:]}"