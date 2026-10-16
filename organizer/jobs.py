"""The slow steps, as plain functions the UI runs on a background thread.

Keeping them here (instead of inside widget code) means they can be tested
without a window. None of them touches a widget.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Iterable

from .categories import ClassificationRules
from .executor import ExecutionProgress, ExecutionResult, execute_plan
from .history import HistoryStore, RunRecord
from .planner import Plan, PlanOptions, build_plan
from .scanner import ScanResult
from .selection import Selection, filter_scan
from .undo import UndoCheck, preflight


def build_preview(
    scan: ScanResult,
    selected: Selection | Iterable[str],
    rules: ClassificationRules,
    destination: str | os.PathLike[str],
    options: PlanOptions,
) -> Plan:
    """Plan only what is selected (file types or individual files). Reads the disk; changes nothing."""
    return build_plan(filter_scan(scan, selected), rules, destination, options)


@dataclass(frozen=True)
class RunJobResult:
    result: ExecutionResult | None = None  # set when the plan was executed
    changed_plan: Plan | None = None  # set when the disk changed and nothing was run


def run_plan_job(
    scan: ScanResult,
    selected: Selection | Iterable[str],
    rules: ClassificationRules,
    destination: str | os.PathLike[str],
    options: PlanOptions,
    plan: Plan,
    history: HistoryStore,
    *,
    progress: Callable[[ExecutionProgress], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> RunJobResult:
    """Re-check the destination, then run ``plan``.

    The plan is rebuilt first. If it differs from the one the user previewed
    (for example a file appeared in the destination), nothing is executed and
    the fresh plan is returned so the user can review it. The executor then
    re-checks every individual file again before touching it.
    """
    fresh = build_preview(scan, selected, rules, destination, options)
    if fresh.fingerprint() != plan.fingerprint():
        return RunJobResult(changed_plan=fresh)
    result = execute_plan(plan, history, progress=progress, should_cancel=should_cancel)
    return RunJobResult(result=result)


@dataclass(frozen=True)
class UndoPreflight:
    run: RunRecord
    checks: tuple[UndoCheck, ...]


def undo_preflight(store: HistoryStore, run_id: str) -> UndoPreflight:
    """Read-only check of what could be undone for a run right now."""
    run = store.load_run(run_id)
    return UndoPreflight(run, tuple(preflight(run)))