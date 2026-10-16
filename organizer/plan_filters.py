"""Filtering the preview table. Pure functions; nothing here touches the disk."""

from __future__ import annotations

from typing import Iterable

from .planner import ConflictKind, Plan, PlannedOperation

STATUS_OPTIONS = ("All", "Ready", "Renamed", "Skipped", "Blocked", "Conflicts")


def _matches_status(item: PlannedOperation, option: str) -> bool:
    if option == "All":
        return True
    if option == "Conflicts":
        return item.conflict is not ConflictKind.NONE
    return item.status.value == option.lower()


def filter_items(
    items: Iterable[PlannedOperation],
    *,
    text: str = "",
    status: str = "All",
    category: str | None = None,
    extension: str | None = None,
) -> list[PlannedOperation]:
    """Filter planned operations.

    ``category`` and ``extension`` of ``None`` mean "any". Use ``extension=""``
    for files without an extension. ``text`` matches the source path, the
    target path and the note, ignoring case.
    """
    needle = text.strip().casefold()
    result: list[PlannedOperation] = []
    for item in items:
        if not _matches_status(item, status):
            continue
        if category is not None and item.category != category:
            continue
        if extension is not None and item.extension != extension:
            continue
        if needle and needle not in f"{item.source} {item.target or ''} {item.message}".casefold():
            continue
        result.append(item)
    return result


def plan_categories(plan: Plan) -> list[str]:
    return sorted({item.category for item in plan.items}, key=str.casefold)


def plan_extensions(plan: Plan) -> list[str]:
    return sorted({item.extension for item in plan.items})