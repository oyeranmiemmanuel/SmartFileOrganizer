"""UI-independent state and row builders for the preview, run and history screens."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from ..executor import ExecutionResult
from ..history import RunSummary
from ..planner import Action, ConflictPolicy, Layout, Plan, PlanOptions, PlannedOperation, Status
from ..reports import result_headline


class PlanStatus(str, Enum):
    NONE = "none"
    BUILDING = "building"
    READY = "ready"
    ERROR = "error"


class RunStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"


ACTION_CHOICES = {"Move": Action.MOVE, "Copy": Action.COPY}
CONFLICT_CHOICES = {
    "Rename (keep both files)": ConflictPolicy.RENAME,
    "Skip conflicting files": ConflictPolicy.SKIP,
}
LAYOUT_CHOICES = {
    "Flatten into category folders": Layout.FLATTEN,
    "Keep subfolder structure": Layout.PRESERVE_STRUCTURE,
}
DEFAULT_ACTION = "Move"
DEFAULT_CONFLICT = "Rename (keep both files)"
DEFAULT_LAYOUT = "Flatten into category folders"


def plan_options(action_label: str, conflict_label: str, layout_label: str) -> PlanOptions:
    """Turn the labels shown in the interface into engine options (unknown labels use the defaults)."""
    return PlanOptions(
        action=ACTION_CHOICES.get(action_label, Action.MOVE),
        conflict_policy=CONFLICT_CHOICES.get(conflict_label, ConflictPolicy.RENAME),
        layout=LAYOUT_CHOICES.get(layout_label, Layout.FLATTEN),
    )


def plan_badge(status: PlanStatus) -> tuple[str, str]:
    return {
        PlanStatus.NONE: ("No preview", "neutral"),
        PlanStatus.BUILDING: ("Building preview…", "info"),
        PlanStatus.READY: ("Preview ready", "success"),
        PlanStatus.ERROR: ("Preview failed", "danger"),
    }[status]


def run_badge(
    status: RunStatus, result: ExecutionResult | None = None, cancelling: bool = False
) -> tuple[str, str]:
    if status is RunStatus.RUNNING:
        return ("Cancelling…", "warning") if cancelling else ("Running…", "info")
    if status is RunStatus.ERROR:
        return "Operation failed", "danger"
    if status is RunStatus.FINISHED and result is not None:
        return result_headline(result)
    return "No operation yet", "neutral"


_STATUS_TEXT = {
    Status.READY: "Ready",
    Status.RENAMED: "Renamed",
    Status.SKIPPED: "Skipped",
    Status.BLOCKED: "Blocked",
}


def _relative(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def preview_row(item: PlannedOperation, plan: Plan) -> tuple:
    """(status, file, goes to, category, size, note, index) for the preview table."""
    goes_to = _relative(item.target, plan.destination) if item.target else "—"
    return (
        _STATUS_TEXT[item.status],
        _relative(item.source, plan.source),
        goes_to,
        item.category,
        item.size,
        item.message,
        item.index,
    )


_RUN_STATUS_TEXT = {"completed": "Completed", "cancelled": "Cancelled", "interrupted": "Interrupted"}


def history_row(summary: RunSummary) -> tuple:
    """(started, action, source, destination, done, skipped, failed, undone, status, run id)."""
    return (
        summary.started_at.replace("T", " ")[:19],
        summary.action.capitalize(),
        summary.source,
        summary.destination,
        summary.done,
        summary.skipped,
        summary.failed,
        summary.undone,
        _RUN_STATUS_TEXT.get(summary.status, summary.status.capitalize()),
        summary.run_id,
    )