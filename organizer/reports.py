"""Plain-text wording for confirmations and reports. Pure functions."""

from __future__ import annotations

from typing import NamedTuple, Sequence

from .executor import ExecutionResult, OutcomeStatus
from .formatting import format_bytes, plural
from .history import (
    ENTRY_CANCELLED,
    ENTRY_DONE,
    ENTRY_FAILED,
    ENTRY_SKIPPED,
    UNDO_DONE,
    RunRecord,
)
from .planner import Action, Plan
from .undo import UndoCheck, UndoResult

OUTCOME_LABELS = {
    OutcomeStatus.DONE: "Done",
    OutcomeStatus.SKIPPED: "Skipped",
    OutcomeStatus.FAILED: "Failed",
    OutcomeStatus.CANCELLED: "Not run",
}


def confirmation_text(plan: Plan) -> str:
    """The text of the confirmation dialog shown before a run."""
    summary = plan.summary()
    move = plan.options.action is Action.MOVE
    count = summary.ready + summary.renamed
    lines = [
        f"{'Move' if move else 'Copy'} {plural(count, 'file')} ({format_bytes(summary.executable_bytes)})?",
        "",
        f"From:  {plan.source}",
        f"To:      {plan.destination}",
        "",
    ]
    if summary.renamed:
        lines.append(f"{plural(summary.renamed, 'file')} will be renamed because the name is already taken.")
    if summary.skipped:
        lines.append(f"{plural(summary.skipped, 'file')} will be skipped because of a name conflict.")
    if summary.blocked:
        lines.append(f"{plural(summary.blocked, 'file')} cannot be processed (blocked).")
    lines.append("Existing files are never overwritten.")
    if move:
        lines.append("You can undo this from History while the files are unchanged.")
    else:
        lines.append("The copies can be removed again from History while they are unchanged.")
    return "\n".join(lines)


def result_headline(result: ExecutionResult) -> tuple[str, str]:
    """(text, badge kind) summarising how a run ended."""
    if result.cancelled:
        return "Cancelled: some files were not processed", "warning"
    if result.failed:
        return "Completed with errors", "danger"
    if result.skipped:
        return "Completed: some files were skipped", "warning"
    return "Completed", "success"


def problem_rows(result: ExecutionResult) -> list[tuple[str, str, str]]:
    """(result label, source path, message) for every file that was not processed."""
    return [
        (OUTCOME_LABELS[outcome.status], str(outcome.source), outcome.message)
        for outcome in result.outcomes
        if outcome.status is not OutcomeStatus.DONE
    ]


def report_text(result: ExecutionResult, plan: Plan, limit: int = 500) -> str:
    verb = "Moved" if plan.options.action is Action.MOVE else "Copied"
    lines = [
        "Smart File Organizer: operation report",
        f"Run ID: {result.run_id}",
        f"Source: {plan.source}",
        f"Destination: {plan.destination}",
        f"Action: {plan.options.action.value}",
        "",
        f"{verb}: {result.succeeded:,} ({format_bytes(result.bytes_done)})",
        f"Skipped: {result.skipped:,}",
        f"Failed: {result.failed:,}",
        f"Not run (cancelled): {result.not_run:,}",
    ]
    if result.created_dirs:
        lines.append(f"Folders created: {len(result.created_dirs):,}")
    problems = problem_rows(result)
    if problems:
        lines += ["", "Files that were not processed:"]
        for label, source, message in problems[:limit]:
            lines.append(f"  [{label}] {source}" + (f" - {message}" if message else ""))
        if len(problems) > limit:
            lines.append(f"  ... and {len(problems) - limit:,} more")
    return "\n".join(lines)


def run_details_text(run: RunRecord, limit: int = 500) -> str:
    lines = [
        f"Run ID: {run.run_id}",
        f"Started: {run.started_at}",
        f"Finished: {run.finished_at or '(did not finish)'}",
        f"Status: {run.status}",
        f"Action: {run.action}   Conflicts: {run.conflict_policy}   Layout: {run.layout}",
        f"Source: {run.source}",
        f"Destination: {run.destination}",
        "",
        (
            f"Done: {run.count(ENTRY_DONE):,}   Skipped: {run.count(ENTRY_SKIPPED):,}   "
            f"Failed: {run.count(ENTRY_FAILED):,}   Cancelled: {run.count(ENTRY_CANCELLED):,}"
        ),
        f"Undo state: {run.undo_state}",
    ]
    if run.skipped_lines:
        lines.append(f"{run.skipped_lines:,} damaged history lines were ignored.")
    lines += ["", "Files:"]
    for entry in run.entries[:limit]:
        line = f"  [{entry.status}] {entry.source}"
        if entry.target:
            line += f"  ->  {entry.target}"
        lines.append(line)
        if entry.message:
            lines.append(f"      {entry.message}")
        if entry.undo_status:
            lines.append(f"      undo: {entry.undo_status} {entry.undo_message}".rstrip())
    if len(run.entries) > limit:
        lines.append(f"  ... and {len(run.entries) - limit:,} more")
    return "\n".join(lines)


class PreflightSummary(NamedTuple):
    ok: int
    blocked: int
    reasons: list[str]


def preflight_summary(checks: Sequence[UndoCheck]) -> PreflightSummary:
    blocked = [check for check in checks if not check.ok]
    reasons = list(dict.fromkeys(check.reason for check in blocked))[:8]
    return PreflightSummary(sum(1 for check in checks if check.ok), len(blocked), reasons)


def undo_confirmation_text(summary: PreflightSummary, action: str) -> str:
    what = "move back" if action == "move" else "remove the copies of"
    lines = [f"Undo this run? The app will {what} {plural(summary.ok, 'file')}."]
    if summary.blocked:
        lines += ["", f"{plural(summary.blocked, 'file')} cannot be undone safely and will be left alone:"]
        lines += [f"  \u2022 {reason}" for reason in summary.reasons]
    lines += ["", "Nothing is ever overwritten."]
    return "\n".join(lines)


def undo_report_text(result: UndoResult, limit: int = 200) -> str:
    lines = [
        "Undo report",
        f"Run ID: {result.run_id}",
        "",
        f"Undone: {result.undone:,}",
        f"Blocked (left alone): {result.blocked:,}",
        f"Failed: {result.failed:,}",
    ]
    if result.cancelled:
        lines.append("The undo was cancelled before it finished.")
    if result.removed_dirs:
        lines.append(f"Empty folders removed: {len(result.removed_dirs):,}")
    problems = [outcome for outcome in result.outcomes if outcome.status != UNDO_DONE]
    if problems:
        lines += ["", "Files that were not restored:"]
        for outcome in problems[:limit]:
            lines.append(f"  [{outcome.status}] {outcome.source}")
            if outcome.message:
                lines.append(f"      {outcome.message}")
        if len(problems) > limit:
            lines.append(f"  ... and {len(problems) - limit:,} more")
    return "\n".join(lines)