"""UI-independent helpers (no tkinter or customtkinter imports, so they are easy to test)."""

from __future__ import annotations

from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Iterable

from ..planner import validate_paths
from ..scanner import (
    SKIP_EXCLUDED_DIR,
    SKIP_EXCLUDED_PATH,
    SKIP_HIDDEN,
    SKIP_LINK,
    SKIP_NOT_REGULAR,
    SKIP_SYSTEM,
    ScanResult,
    SkippedEntry,
)


class ScanStatus(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    DONE = "done"
    CANCELLED = "cancelled"
    ERROR = "error"


def status_badge(status: ScanStatus, cancelling: bool = False) -> tuple[str, str]:
    """Text and badge kind for a scan status."""
    if status is ScanStatus.SCANNING:
        return ("Cancelling…", "warning") if cancelling else ("Scanning…", "info")
    return {
        ScanStatus.IDLE: ("Ready to scan", "neutral"),
        ScanStatus.DONE: ("Scan complete", "success"),
        ScanStatus.CANCELLED: ("Scan cancelled", "warning"),
        ScanStatus.ERROR: ("Scan failed", "danger"),
    }[status]


def validation_messages(source: str, destination: str) -> list[tuple[str, str]]:
    """(kind, text) lines describing the chosen folders. Reads the disk, changes nothing."""
    source, destination = source.strip(), destination.strip()
    if not source:
        return [("muted", "Choose the folder you want to organize.")]
    if not Path(source).is_dir():
        return [("error", f"The source folder does not exist or is not a folder: {source}")]
    messages: list[tuple[str, str]] = [("ok", "Source folder found.")]
    if not destination:
        messages.append(("muted", "No destination yet. It is needed later, for the preview step."))
        return messages
    check = validate_paths(source, destination)
    messages.extend(("error", text) for text in check.errors)
    messages.extend(("warning", text) for text in check.warnings)
    if check.ok:
        messages.append(("ok", "Destination looks valid. Files will go into folders inside it."))
    return messages


SKIP_LABELS = {
    SKIP_HIDDEN: "hidden items",
    SKIP_SYSTEM: "system items",
    SKIP_LINK: "links and junctions",
    SKIP_EXCLUDED_DIR: "excluded folders",
    SKIP_EXCLUDED_PATH: "the destination folder",
    SKIP_NOT_REGULAR: "special files",
}


def skip_label(reason: str) -> str:
    return SKIP_LABELS.get(reason, reason)


def summarize_skipped(skipped: Iterable[SkippedEntry]) -> list[tuple[str, int]]:
    """(label, count) pairs, most common first."""
    counts = Counter(entry.reason for entry in skipped)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [(skip_label(reason), count) for reason, count in ordered]


def issues_text(scan: ScanResult, limit: int = 200) -> str:
    """Readable report of everything a scan skipped or could not read."""
    lines: list[str] = []
    if scan.skipped:
        lines.append(f"Skipped items ({len(scan.skipped):,})")
        for label, count in summarize_skipped(scan.skipped):
            lines.append(f"  {count:,} {label}")
        lines.append("")
        lines.append("Examples:")
        for entry in scan.skipped[:limit]:
            lines.append(f"  [{skip_label(entry.reason)}] {entry.path}")
        if len(scan.skipped) > limit:
            lines.append(f"  ... and {len(scan.skipped) - limit:,} more")
    if scan.errors:
        if lines:
            lines.append("")
        lines.append(f"Errors ({len(scan.errors):,})")
        for error in scan.errors[:limit]:
            lines.append(f"  {error.path}: {error.message}")
        if len(scan.errors) > limit:
            lines.append(f"  ... and {len(scan.errors) - limit:,} more")
    return "\n".join(lines) if lines else "Nothing was skipped and no errors occurred."