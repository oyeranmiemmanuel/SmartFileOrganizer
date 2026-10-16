"""Persistent operation history.

Each run is one append-only JSON Lines file, ``<history dir>/<run_id>.jsonl``.
Lines are only ever added, and each is flushed as it is written, so a crash or
power cut in the middle of a run still leaves a readable record of everything
completed up to that point. Undo relies on that record.

Line types (every line is one JSON object, ``"type"`` first):

* ``run``     header: source, destination, action, plan fingerprint
* ``intent``  written *before* an operation starts
* ``entry``   the final outcome of one operation
* ``dirs``    folders this run created (so undo can remove them if empty)
* ``end``     run finished: status and counts
* ``undo``    the outcome of undoing one entry

An ``intent`` with no later ``entry`` means the app stopped mid-operation. Such
an entry is shown as ``started`` and is never undone automatically, because its
state is uncertain.

Unknown line types and damaged lines are skipped, so newer or partly written
files stay readable.
"""

from __future__ import annotations

import csv
import json
import os
import re
import secrets
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

FORMAT_VERSION = 1
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_FSYNC_EVERY = 50

# Entry statuses
ENTRY_STARTED = "started"
ENTRY_DONE = "done"
ENTRY_SKIPPED = "skipped"
ENTRY_FAILED = "failed"
ENTRY_CANCELLED = "cancelled"

# Run statuses
RUN_COMPLETED = "completed"
RUN_CANCELLED = "cancelled"
RUN_INTERRUPTED = "interrupted"  # no "end" line: the app stopped unexpectedly

# Undo statuses
UNDO_DONE = "undone"
UNDO_BLOCKED = "blocked"
UNDO_FAILED = "failed"


class HistoryError(Exception):
    """A history file is missing, unreadable or has an invalid name."""


def default_history_dir() -> Path:
    """Provisional per-user location (final choice is made in Phase 5)."""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "SmartFileOrganizer" / "history"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True)
class EntryRecord:
    index: int
    action: str  # "move" | "copy"
    source: str
    target: str | None = None
    desired_target: str | None = None
    status: str = ENTRY_STARTED
    message: str = ""
    size: int = 0
    source_mtime_ns: int | None = None  # as observed just before the operation
    target_size: int | None = None  # as observed just after the operation
    target_mtime_ns: int | None = None
    undo_status: str | None = None
    undo_message: str = ""
    undo_at: str | None = None

    @property
    def undoable(self) -> bool:
        return self.status == ENTRY_DONE and self.undo_status != UNDO_DONE


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    started_at: str
    source: str
    destination: str
    action: str
    conflict_policy: str
    layout: str
    fingerprint: str
    total_items: int
    status: str = RUN_INTERRUPTED
    finished_at: str | None = None
    entries: tuple[EntryRecord, ...] = ()
    created_dirs: tuple[str, ...] = ()
    skipped_lines: int = 0  # damaged lines that were ignored while reading

    def count(self, status: str) -> int:
        return sum(1 for e in self.entries if e.status == status)

    @property
    def undoable_entries(self) -> tuple[EntryRecord, ...]:
        return tuple(e for e in self.entries if e.undoable)

    @property
    def undo_state(self) -> str:
        """"none" (nothing undone), "partial", "complete", or "nothing_to_undo"."""
        done = [e for e in self.entries if e.status == ENTRY_DONE]
        if not done:
            return "nothing_to_undo"
        undone = sum(1 for e in done if e.undo_status == UNDO_DONE)
        if undone == 0:
            return "none"
        return "complete" if undone == len(done) else "partial"


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    started_at: str
    finished_at: str | None
    source: str
    destination: str
    action: str
    status: str
    total_items: int
    done: int
    skipped: int
    failed: int
    undone: int


def _entry_from_dict(data: dict[str, Any]) -> EntryRecord:
    known = {f.name for f in fields(EntryRecord)}
    return EntryRecord(**{k: v for k, v in data.items() if k in known})


class RunWriter:
    """Appends one run's journal. Use as a context manager."""

    def __init__(self, path: Path, header: dict[str, Any]):
        self.path = path
        self.run_id: str = header["run_id"]
        self._since_sync = 0
        self._file = open(path, "x", encoding="utf-8", newline="\n")
        self._write({"type": "run", "format": FORMAT_VERSION, **header}, sync=True)

    def _write(self, record: dict[str, Any], sync: bool = False) -> None:
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()
        self._since_sync += 1
        if sync or self._since_sync >= _FSYNC_EVERY:
            os.fsync(self._file.fileno())
            self._since_sync = 0

    def intent(self, entry: EntryRecord) -> None:
        """Written before an operation starts; only what is needed to recognize it afterwards."""
        keep = ("index", "action", "source", "target", "size", "source_mtime_ns")
        data = {k: v for k, v in asdict(entry).items() if k in keep}
        self._write({"type": "intent", **data})

    def entry(self, entry: EntryRecord) -> None:
        # Empty fields are omitted to keep large runs small; they read back as defaults.
        data = {k: v for k, v in asdict(entry).items() if v is not None and v != ""}
        self._write({"type": "entry", **data})

    def created_dirs(self, paths: list[str]) -> None:
        if paths:
            self._write({"type": "dirs", "paths": list(paths)})

    def finish(self, status: str, counts: dict[str, int]) -> None:
        self._write(
            {"type": "end", "finished_at": _now(), "status": status, "counts": counts}, sync=True
        )
        self.close()

    def close(self) -> None:
        if not self._file.closed:
            try:
                os.fsync(self._file.fileno())
            finally:
                self._file.close()

    def __enter__(self) -> "RunWriter":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()  # a run left without an "end" line reads back as interrupted


class HistoryStore:
    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)

    # ------------------------------------------------------------------ write

    def start_run(
        self,
        *,
        source: str,
        destination: str,
        action: str,
        conflict_policy: str,
        layout: str,
        fingerprint: str,
        total_items: int,
    ) -> RunWriter:
        self.directory.mkdir(parents=True, exist_ok=True)
        for _ in range(20):
            run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
            try:
                return RunWriter(
                    self.directory / f"{run_id}.jsonl",
                    {
                        "run_id": run_id,
                        "started_at": _now(),
                        "source": source,
                        "destination": destination,
                        "action": action,
                        "conflict_policy": conflict_policy,
                        "layout": layout,
                        "fingerprint": fingerprint,
                        "total_items": total_items,
                    },
                )
            except FileExistsError:
                continue
        raise HistoryError("Could not create a unique history file.")

    def record_undo(
        self, run_id: str, index: int, status: str, message: str = ""
    ) -> None:
        """Append the outcome of undoing one entry."""
        with open(self._path(run_id), "a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {"type": "undo", "index": index, "status": status, "message": message, "at": _now()}
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())

    # ------------------------------------------------------------------- read

    def _path(self, run_id: str) -> Path:
        if not _RUN_ID.match(run_id):
            raise HistoryError(f"Invalid run id: {run_id!r}")
        return self.directory / f"{run_id}.jsonl"

    def _lines(self, path: Path) -> Iterator[str]:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                yield from handle
        except FileNotFoundError:
            raise HistoryError(f"History for run '{path.stem}' was not found.") from None
        except OSError as exc:
            raise HistoryError(f"Cannot read history file '{path}': {exc}") from exc

    def load_run(self, run_id: str) -> RunRecord:
        header: dict[str, Any] | None = None
        entries: dict[int, EntryRecord] = {}
        undo: dict[int, dict[str, Any]] = {}
        dirs: list[str] = []
        end: dict[str, Any] | None = None
        skipped_lines = 0
        for line in self._lines(self._path(run_id)):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                kind = record["type"]
            except (ValueError, KeyError, TypeError):
                skipped_lines += 1
                continue
            try:
                if kind == "run" and header is None:
                    header = record
                elif kind in ("intent", "entry"):
                    entries[record["index"]] = _entry_from_dict(record)
                elif kind == "dirs":
                    dirs.extend(str(p) for p in record["paths"])
                elif kind == "end":
                    end = record
                elif kind == "undo":
                    undo[record["index"]] = record
            except (KeyError, TypeError):
                skipped_lines += 1
        if header is None:
            raise HistoryError(f"History file for run '{run_id}' has no header.")
        for index, event in undo.items():
            if index in entries:
                entries[index] = replace(
                    entries[index],
                    undo_status=event.get("status"),
                    undo_message=str(event.get("message", "")),
                    undo_at=event.get("at"),
                )
        return RunRecord(
            run_id=header["run_id"],
            started_at=header["started_at"],
            source=header["source"],
            destination=header["destination"],
            action=header["action"],
            conflict_policy=header.get("conflict_policy", ""),
            layout=header.get("layout", ""),
            fingerprint=header.get("fingerprint", ""),
            total_items=header.get("total_items", len(entries)),
            status=end["status"] if end else RUN_INTERRUPTED,
            finished_at=end.get("finished_at") if end else None,
            entries=tuple(entries[i] for i in sorted(entries)),
            created_dirs=tuple(dict.fromkeys(dirs)),
            skipped_lines=skipped_lines,
        )

    def list_runs(self) -> list[RunSummary]:
        """Summaries of every readable run, newest first. Damaged files are skipped."""
        if not self.directory.is_dir():
            return []
        summaries = []
        for path in self.directory.glob("*.jsonl"):
            try:
                summaries.append(self._summarize(path.stem))
            except HistoryError:
                continue
        return sorted(summaries, key=lambda s: (s.started_at, s.run_id), reverse=True)

    def _summarize(self, run_id: str) -> RunSummary:
        """Cheap summary: parses only header/end/undo lines unless the run has no end."""
        header: dict[str, Any] | None = None
        end: dict[str, Any] | None = None
        undone: set[int] = set()
        for line in self._lines(self._path(run_id)):
            if line.startswith('{"type": "entry"') or line.startswith('{"type": "intent"') \
                    or line.startswith('{"type": "dirs"'):
                continue
            try:
                record = json.loads(line)
                kind = record["type"]
                if kind == "run" and header is None:
                    header = record
                elif kind == "end":
                    end = record
                elif kind == "undo" and record.get("status") == UNDO_DONE:
                    undone.add(record["index"])
            except (ValueError, KeyError, TypeError):
                continue
        if header is None:
            raise HistoryError(f"History file for run '{run_id}' has no header.")
        if end is None:  # interrupted run: counts need the entries
            run = self.load_run(run_id)
            return RunSummary(
                run.run_id, run.started_at, None, run.source, run.destination, run.action,
                RUN_INTERRUPTED, run.total_items, run.count(ENTRY_DONE),
                run.count(ENTRY_SKIPPED) + run.count(ENTRY_CANCELLED), run.count(ENTRY_FAILED),
                sum(1 for e in run.entries if e.undo_status == UNDO_DONE),
            )
        counts = end.get("counts", {})
        return RunSummary(
            run_id=header["run_id"],
            started_at=header["started_at"],
            finished_at=end.get("finished_at"),
            source=header["source"],
            destination=header["destination"],
            action=header["action"],
            status=end["status"],
            total_items=header.get("total_items", 0),
            done=counts.get("done", 0),
            skipped=counts.get("skipped", 0) + counts.get("cancelled", 0),
            failed=counts.get("failed", 0),
            undone=len(undone),
        )


def export_run_csv(run: RunRecord, path: str | os.PathLike[str]) -> None:
    """Write a run as CSV (the original app's history format, plus status columns)."""
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:  # BOM: Excel opens it correctly
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "action", "source", "target", "status", "message", "undo_status"])
        for entry in run.entries:
            writer.writerow(
                [run.started_at, entry.action, entry.source, entry.target or "",
                 entry.status, entry.message, entry.undo_status or ""]
            )
