"""Safe undo of a recorded run.

Undo never guesses. Before reversing an entry it checks that the files still
look exactly as the run left them, and it refuses (``blocked``) rather than
risk losing data:

* Undo a **move**: the moved file must still exist at its target with the size
  and timestamp recorded at the time, and the original location must be
  free. Nothing is ever overwritten.
* Undo a **copy**: the copy must be unchanged, and the original must still
  exist and be unchanged, so removing the copy can never delete the only
  version of a file.
* Entries whose state is uncertain (the app stopped mid-operation) are left
  alone and reported.

Folders the run created are removed afterwards, but only if they are empty.

Limitation: "unchanged" means same size and same modification time. A change
that preserves both would not be noticed.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import fileops
from .history import (
    ENTRY_DONE,
    ENTRY_STARTED,
    UNDO_BLOCKED,
    UNDO_DONE,
    UNDO_FAILED,
    EntryRecord,
    HistoryStore,
    RunRecord,
)
from .planner import ConflictPolicy


@dataclass(frozen=True)
class UndoCheck:
    index: int
    action: str
    source: str
    target: str | None
    ok: bool
    reason: str = ""


@dataclass(frozen=True)
class UndoOutcome:
    index: int
    source: str
    target: str | None
    status: str  # "undone" | "blocked" | "failed" | "cancelled"
    message: str = ""


@dataclass(frozen=True)
class UndoProgress:
    total: int
    completed: int
    undone: int
    blocked: int
    failed: int
    current: str | None


@dataclass
class UndoResult:
    run_id: str
    outcomes: list[UndoOutcome] = field(default_factory=list)
    removed_dirs: list[str] = field(default_factory=list)
    cancelled: bool = False

    def _count(self, status: str) -> int:
        return sum(1 for o in self.outcomes if o.status == status)

    @property
    def undone(self) -> int:
        return self._count(UNDO_DONE)

    @property
    def blocked(self) -> int:
        return self._count(UNDO_BLOCKED)

    @property
    def failed(self) -> int:
        return self._count(UNDO_FAILED)


def _regular_file_stat(path: str) -> os.stat_result | str:
    """The file's stat, or a human-readable reason it cannot be trusted."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return "no longer exists"
    except OSError as exc:
        return f"cannot be read ({exc})"
    if not stat.S_ISREG(info.st_mode) or fileops.is_link(path):
        return "is no longer a regular file"
    return info


def check_entry(entry: EntryRecord) -> UndoCheck:
    """Read-only check of whether one entry can be undone right now."""

    def result(ok: bool, reason: str = "") -> UndoCheck:
        return UndoCheck(entry.index, entry.action, entry.source, entry.target, ok, reason)

    if entry.status == ENTRY_STARTED:
        return result(False, "The app stopped while this file was being processed; its state is uncertain. Check both locations by hand.")
    if entry.status != ENTRY_DONE:
        return result(False, "Nothing was changed for this file.")
    if entry.undo_status == UNDO_DONE:
        return result(False, "Already undone.")
    if not entry.target or entry.target_size is None or entry.target_mtime_ns is None:
        return result(False, "No verification data was recorded for this file.")

    target = _regular_file_stat(entry.target)
    if isinstance(target, str):
        return result(False, f"The moved/copied file {target}: {entry.target}")
    if target.st_size != entry.target_size or target.st_mtime_ns != entry.target_mtime_ns:
        return result(False, f"The file at the target was modified after the operation: {entry.target}")

    if entry.action == "move":
        if os.path.lexists(entry.source):
            return result(False, f"Something now exists at the original location, so the file cannot be restored there: {entry.source}")
        return result(True)

    original = _regular_file_stat(entry.source)
    if isinstance(original, str):
        return result(False, f"The original file {original}; the copy is now the only version, so it was kept: {entry.source}")
    if entry.source_mtime_ns is not None and (
        original.st_size != entry.size or original.st_mtime_ns != entry.source_mtime_ns
    ):
        return result(False, f"The original file was modified after it was copied; the copy was kept: {entry.source}")
    return result(True)


def preflight(run: RunRecord) -> list[UndoCheck]:
    """Checks for every entry that is still undoable. Reads only; changes nothing."""
    return [check_entry(e) for e in run.entries if e.status in (ENTRY_DONE, ENTRY_STARTED) and e.undo_status != UNDO_DONE]


def undo_run(
    store: HistoryStore,
    run_id: str,
    *,
    progress: Callable[[UndoProgress], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> UndoResult:
    """Undo a recorded run, newest operation first. Safe to run more than once."""
    run = store.load_run(run_id)
    entries = [e for e in run.entries if e.status in (ENTRY_DONE, ENTRY_STARTED) and e.undo_status != UNDO_DONE]
    entries.sort(key=lambda e: e.index, reverse=True)
    result = UndoResult(run_id=run_id)

    def notify(current: str | None) -> None:
        if progress is None:
            return
        try:
            progress(UndoProgress(len(entries), len(result.outcomes), result.undone,
                                  result.blocked, result.failed, current))
        except Exception:
            pass

    notify(None)
    for entry in entries:
        if should_cancel is not None and should_cancel():
            result.cancelled = True
            break
        notify(entry.target)
        check = check_entry(entry)  # re-checked immediately before acting
        if not check.ok:
            status, message = UNDO_BLOCKED, check.reason
        else:
            try:
                status, message = _undo_entry(entry)
            except Exception as exc:
                status, message = UNDO_FAILED, f"{type(exc).__name__}: {exc}"
        store.record_undo(run_id, entry.index, status, message)
        result.outcomes.append(UndoOutcome(entry.index, entry.source, entry.target, status, message))
        notify(None)

    result.removed_dirs = _remove_created_dirs(run)
    notify(None)
    return result


def _undo_entry(entry: EntryRecord) -> tuple[str, str]:
    assert entry.target is not None
    if entry.action == "copy":
        os.unlink(entry.target)
        return UNDO_DONE, "The copy was removed."

    source = Path(entry.source)
    os.makedirs(source.parent, exist_ok=True)
    claimed = fileops.claim_target(source, ConflictPolicy.SKIP)
    if claimed is None:
        return UNDO_BLOCKED, f"Something appeared at the original location, so the file was left where it is: {entry.source}"
    try:
        fileops.move_file(entry.target, claimed)
    except BaseException:
        fileops.release_claim(entry.target, claimed)
        raise
    return UNDO_DONE, "The file was moved back."


def _remove_created_dirs(run: RunRecord) -> list[str]:
    """Remove folders this run created, deepest first, only if they are empty."""
    removed = []
    for folder in sorted(run.created_dirs, key=lambda p: len(Path(p).parts), reverse=True):
        try:
            if os.path.isdir(folder) and not fileops.is_link(folder):
                os.rmdir(folder)  # fails if the folder is not empty
                removed.append(folder)
        except OSError:
            continue
    return removed
