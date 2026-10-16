"""Execute a preview plan: move or copy files safely and journal every step.

The plan is a *proposal*. The disk may have changed since it was built, so
before touching each file this module re-checks, for that file only:

* the source is still a regular file (not a link, not missing),
* its size and modification time still match the preview,
* the destination folder chain contains no links,
* the target name is still free (claimed atomically; see ``fileops``).

A file that fails a check is skipped with an explanation. A file that raises
an error is reported as failed. Neither stops the rest of the run. Existing
files are never overwritten.

Cancellation is honoured between files: the file in progress always finishes
(or fails cleanly), then the remaining files are marked cancelled.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Callable

from . import fileops
from .history import (
    ENTRY_CANCELLED,
    ENTRY_DONE,
    ENTRY_FAILED,
    ENTRY_SKIPPED,
    RUN_CANCELLED,
    RUN_COMPLETED,
    EntryRecord,
    HistoryStore,
)
from .planner import (
    Action,
    ConflictPolicy,
    Plan,
    PlannedOperation,
    PlanValidationError,
    Status,
    validate_paths,
)


class OutcomeStatus(str, Enum):
    DONE = ENTRY_DONE
    SKIPPED = ENTRY_SKIPPED
    FAILED = ENTRY_FAILED
    CANCELLED = ENTRY_CANCELLED


@dataclass(frozen=True)
class OperationOutcome:
    index: int
    source: Path
    target: Path | None  # where the file actually went (may differ from the plan)
    status: OutcomeStatus
    message: str = ""
    size: int = 0


@dataclass(frozen=True)
class ExecutionProgress:
    total: int  # operations in the plan, including ones that will be skipped
    completed: int  # operations finished so far (any outcome)
    succeeded: int
    skipped: int
    failed: int
    bytes_total: int  # bytes of all executable operations
    bytes_done: int  # bytes of executable operations finished so far
    current: Path | None  # file being processed; None for the final update


@dataclass
class ExecutionResult:
    run_id: str
    outcomes: list[OperationOutcome] = field(default_factory=list)
    cancelled: bool = False
    created_dirs: list[str] = field(default_factory=list)
    callback_errors: int = 0

    def _count(self, status: OutcomeStatus) -> int:
        return sum(1 for o in self.outcomes if o.status is status)

    @property
    def succeeded(self) -> int:
        return self._count(OutcomeStatus.DONE)

    @property
    def skipped(self) -> int:
        return self._count(OutcomeStatus.SKIPPED)

    @property
    def failed(self) -> int:
        return self._count(OutcomeStatus.FAILED)

    @property
    def not_run(self) -> int:
        return self._count(OutcomeStatus.CANCELLED)

    @property
    def bytes_done(self) -> int:
        return sum(o.size for o in self.outcomes if o.status is OutcomeStatus.DONE)


def _missing_ancestors(folder: Path) -> list[Path]:
    """Folders that do not exist yet on the way to ``folder``, outermost first."""
    missing: list[Path] = []
    current = folder
    while not os.path.lexists(current) and current.parent != current:
        missing.append(current)
        current = current.parent
    return missing[::-1]


def _link_in_chain(destination: Path, folder: Path) -> Path | None:
    """First existing folder between ``destination`` and ``folder`` that is a link."""
    current = folder
    while True:
        if os.path.lexists(current) and fileops.is_link(current):
            return current
        if current == destination or current.parent == current:
            return None
        current = current.parent


def _check_source(item: PlannedOperation) -> str | None:
    """Return why the source can no longer be processed, or None if it is fine."""
    try:
        info = os.lstat(item.source)
    except FileNotFoundError:
        return "The file no longer exists."
    except OSError as exc:
        return f"The file cannot be read: {exc}"
    if not stat.S_ISREG(info.st_mode) or fileops.is_link(item.source):
        return "The path is no longer a regular file."
    if info.st_size != item.size or info.st_mtime_ns != item.mtime_ns:
        return "The file changed after the preview was built. Scan again to include its current version."
    return None


def execute_plan(
    plan: Plan,
    history: HistoryStore,
    *,
    progress: Callable[[ExecutionProgress], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ExecutionResult:
    """Run ``plan`` and record it in ``history``. Returns what happened to every item.

    Raises ``PlanValidationError`` before touching anything if the source or
    destination is no longer valid.
    """
    validation = validate_paths(plan.source, plan.destination)
    if not validation.ok:
        raise PlanValidationError(validation.errors)

    action = plan.options.action
    policy = plan.options.conflict_policy
    items = plan.items
    total = len(items)
    bytes_total = sum(i.size for i in items if i.executable)

    writer = history.start_run(
        source=str(plan.source),
        destination=str(plan.destination),
        action=action.value,
        conflict_policy=policy.value,
        layout=plan.options.layout.value,
        fingerprint=plan.fingerprint(),
        total_items=total,
    )
    result = ExecutionResult(run_id=writer.run_id)
    state = {"bytes_done": 0}

    def notify(current: Path | None) -> None:
        if progress is None:
            return
        update = ExecutionProgress(
            total=total,
            completed=len(result.outcomes),
            succeeded=result.succeeded,
            skipped=result.skipped,
            failed=result.failed,
            bytes_total=bytes_total,
            bytes_done=state["bytes_done"],
            current=current,
        )
        try:
            progress(update)
        except Exception:  # a broken UI callback must not abort file operations
            result.callback_errors += 1

    def record(outcome: OperationOutcome, entry: EntryRecord) -> None:
        result.outcomes.append(outcome)
        writer.entry(entry)
        if outcome.status is OutcomeStatus.DONE and items[outcome.index].executable:
            state["bytes_done"] += outcome.size

    with writer:
        notify(None)
        for position, item in enumerate(items):
            base = EntryRecord(
                index=item.index,
                action=action.value,
                source=str(item.source),
                desired_target=str(item.desired_target),
                size=item.size,
                source_mtime_ns=item.mtime_ns,
            )

            if should_cancel is not None and should_cancel():
                result.cancelled = True
                for rest in items[position:]:
                    entry = EntryRecord(
                        index=rest.index, action=action.value, source=str(rest.source),
                        desired_target=str(rest.desired_target), status=ENTRY_CANCELLED,
                        message="Not run: the operation was cancelled.", size=rest.size,
                        source_mtime_ns=rest.mtime_ns,
                    )
                    record(
                        OperationOutcome(rest.index, rest.source, None, OutcomeStatus.CANCELLED,
                                         entry.message, rest.size),
                        entry,
                    )
                notify(None)
                break

            if not item.executable:
                kind = "Blocked" if item.status is Status.BLOCKED else "Skipped"
                message = item.message if item.message.startswith(kind) else f"{kind}. {item.message}"
                entry = replace(base, status=ENTRY_SKIPPED, message=message)
                record(OperationOutcome(item.index, item.source, None, OutcomeStatus.SKIPPED, message,
                                        item.size), entry)
                notify(None)
                continue

            notify(item.source)
            outcome, entry = _run_one(item, base, plan, policy, action, writer, result)
            record(outcome, entry)
            notify(None)

        writer.finish(
            RUN_CANCELLED if result.cancelled else RUN_COMPLETED,
            {
                "done": result.succeeded,
                "skipped": result.skipped,
                "failed": result.failed,
                "cancelled": result.not_run,
            },
        )
    return result


def _run_one(
    item: PlannedOperation,
    base: EntryRecord,
    plan: Plan,
    policy: ConflictPolicy,
    action: Action,
    writer,
    result: ExecutionResult,
) -> tuple[OperationOutcome, EntryRecord]:
    def finish(status: OutcomeStatus, message: str, target: Path | None = None,
               target_stat: os.stat_result | None = None) -> tuple[OperationOutcome, EntryRecord]:
        entry = replace(
            base,
            status=status.value,
            message=message,
            target=str(target) if target else None,
            target_size=target_stat.st_size if target_stat else None,
            target_mtime_ns=target_stat.st_mtime_ns if target_stat else None,
        )
        return OperationOutcome(item.index, item.source, target, status, message, item.size), entry

    stale = _check_source(item)
    if stale:
        return finish(OutcomeStatus.SKIPPED, f"Skipped. {stale}")

    assert item.target is not None  # executable items always have a target
    target_dir = item.target.parent
    link = _link_in_chain(plan.destination, target_dir)
    if link is not None:
        return finish(OutcomeStatus.FAILED, f"The destination folder '{link}' is a link; refusing to write through it.")

    claimed: Path | None = None
    try:
        new_dirs = _missing_ancestors(target_dir)
        if new_dirs:
            os.makedirs(target_dir, exist_ok=True)
            created = [str(p) for p in new_dirs]
            result.created_dirs.extend(created)
            writer.created_dirs(created)

        claimed = fileops.claim_target(item.target, policy, item.extension)
        if claimed is None:
            return finish(OutcomeStatus.SKIPPED,
                          f"Skipped. A file named '{item.target.name}' appeared in the destination after the preview.")

        try:
            writer.intent(replace(base, target=str(claimed)))
            if action is Action.COPY:
                fileops.copy_file(item.source, claimed)
            else:
                fileops.move_file(item.source, claimed)
        except BaseException:
            fileops.release_claim(item.source, claimed)
            raise

        try:
            after = os.stat(claimed)
        except OSError:
            after = None  # undo will refuse this entry because it cannot be verified
        note = "" if claimed == item.target else f"Renamed to '{claimed.name}' because the name was taken after the preview."
        return finish(OutcomeStatus.DONE, note, claimed, after)
    except Exception as exc:
        return finish(OutcomeStatus.FAILED, f"{type(exc).__name__}: {exc}")
