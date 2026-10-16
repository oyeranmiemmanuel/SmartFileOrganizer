"""Destination validation and preview-plan building.

Building a plan only *reads* the file system (directory listings and
``exists``-style checks). It never creates folders or touches files; the
executor that acts on a plan is a later phase and must revalidate everything
immediately before acting, because the disk can change after the preview.

Name comparisons are case-insensitive on every platform: two names that differ
only by case are treated as the same name, which is what Windows does and is
the conservative choice elsewhere.
"""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

from .categories import ClassificationRules, NO_EXTENSION_LABEL
from .paths import is_within, path_key, same_path, sanitize_relative_parts
from .scanner import ScanResult, ScannedFile

# Windows' classic limit is 260 characters including the terminating NUL.
DEFAULT_MAX_PATH_LENGTH = 259 if os.name == "nt" else 4095
MAX_RENAME_ATTEMPTS = 9999


class Action(str, Enum):
    MOVE = "move"
    COPY = "copy"


class Layout(str, Enum):
    """What recursive scans do with the source's folder structure."""

    FLATTEN = "flatten"  # <dest>/<category folder>/<file>
    PRESERVE_STRUCTURE = "preserve"  # <dest>/<category folder>/<relative folders>/<file>


class ConflictPolicy(str, Enum):
    RENAME = "rename"  # keep both: "name (1).ext"
    SKIP = "skip"  # leave the new file where it is


class ConflictKind(str, Enum):
    NONE = "none"
    EXISTS_ON_DISK = "exists_on_disk"
    DUPLICATE_IN_PLAN = "duplicate_in_plan"


class Status(str, Enum):
    READY = "ready"
    RENAMED = "renamed"  # ready, but under a different name than the original
    SKIPPED = "skipped"  # not executed because of the conflict policy
    BLOCKED = "blocked"  # cannot be executed; see ``message``


class PlanValidationError(ValueError):
    def __init__(self, errors: Sequence[str]):
        super().__init__("; ".join(errors))
        self.errors = tuple(errors)


@dataclass(frozen=True)
class PlanOptions:
    action: Action = Action.MOVE
    conflict_policy: ConflictPolicy = ConflictPolicy.RENAME
    layout: Layout = Layout.FLATTEN
    max_path_length: int = DEFAULT_MAX_PATH_LENGTH


@dataclass(frozen=True)
class PathValidation:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class PlannedOperation:
    index: int  # stable position in the plan
    source: Path
    desired_target: Path  # where the rules want the file
    target: Path | None  # final destination; None unless READY or RENAMED
    action: Action
    category: str
    folder: str
    extension: str
    classification_reason: str
    size: int
    mtime_ns: int
    conflict: ConflictKind
    status: Status
    message: str = ""

    @property
    def executable(self) -> bool:
        return self.status in (Status.READY, Status.RENAMED)


@dataclass(frozen=True)
class PlanSummary:
    total: int
    ready: int
    renamed: int
    skipped: int
    blocked: int
    conflicts: int
    executable_bytes: int
    per_category: dict[str, int]  # executable operations per category


@dataclass(frozen=True)
class Plan:
    source: Path
    destination: Path
    options: PlanOptions
    items: tuple[PlannedOperation, ...]
    warnings: tuple[str, ...] = ()

    @property
    def executable_items(self) -> tuple[PlannedOperation, ...]:
        return tuple(item for item in self.items if item.executable)

    def summary(self) -> PlanSummary:
        by_status = Counter(item.status for item in self.items)
        executable = self.executable_items
        return PlanSummary(
            total=len(self.items),
            ready=by_status[Status.READY],
            renamed=by_status[Status.RENAMED],
            skipped=by_status[Status.SKIPPED],
            blocked=by_status[Status.BLOCKED],
            conflicts=sum(1 for i in self.items if i.conflict is not ConflictKind.NONE),
            executable_bytes=sum(i.size for i in executable),
            per_category=dict(sorted(Counter(i.category for i in executable).items())),
        )

    def fingerprint(self) -> str:
        """Hash identifying exactly what this plan would do.

        Identical inputs always produce an identical fingerprint. It covers each
        operation's source, target, status, size and modification time, so an
        executor can detect that it is not running the plan the user previewed.
        """
        digest = hashlib.sha256()
        digest.update(f"{self.options.action.value}\n{self.source}\n{self.destination}\n".encode())
        for item in self.items:
            line = (
                f"{item.index}|{item.source}|{item.target}|{item.status.value}|"
                f"{item.size}|{item.mtime_ns}\n"
            )
            digest.update(line.encode("utf-8", "surrogateescape"))
        return digest.hexdigest()


@dataclass(frozen=True)
class ExtensionSummary:
    extension: str  # "" for files without one
    label: str  # ".pdf" or "(no extension)"
    count: int
    total_size: int
    category: str
    folder: str


def validate_paths(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> PathValidation:
    """Check a source/destination pair without touching the disk (reads only)."""
    errors: list[str] = []
    warnings: list[str] = []
    source_text, destination_text = os.fspath(source).strip(), os.fspath(destination).strip()

    if not source_text:
        errors.append("Choose a source folder.")
    elif not Path(source_text).is_dir():
        errors.append(f"The source folder does not exist or is not a folder: {source_text}")
    if not destination_text:
        errors.append("Choose a destination folder.")
    if errors:
        return PathValidation(tuple(errors), ())

    src, dst = Path(source_text), Path(destination_text)
    if same_path(src, dst):
        errors.append("The destination must be different from the source folder.")
    elif is_within(dst, src):
        errors.append(
            "The destination cannot be inside the source folder. Choose a folder outside it "
            "so the organizer never rescans its own output."
        )
    elif is_within(src, dst):
        errors.append("The destination cannot contain the source folder (it is a parent of it).")
    if dst.exists() and not dst.is_dir():
        errors.append(f"The destination exists but is not a folder: {dst}")

    absolute_source = Path(os.path.abspath(src))
    if absolute_source.parent == absolute_source:
        warnings.append("The source is a drive root. Scanning a whole drive is slow and risky.")
    if len(os.path.abspath(dst)) > 200:
        warnings.append("The destination path is long; some files may exceed the path-length limit.")
    existing = Path(os.path.abspath(dst))
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent
    if existing.exists() and not os.access(existing, os.W_OK):
        warnings.append(f"You may not have permission to write to: {existing}")
    return PathValidation(tuple(errors), tuple(warnings))


def rename_candidate(name: str, extension: str, number: int) -> str:
    split = len(name)
    if extension and name[-len(extension):].lower() == extension:
        split = len(name) - len(extension)
    return f"{name[:split]} ({number}){name[split:]}"


class _DiskView:
    """Cached, read-only view of destination folders used to detect conflicts."""

    def __init__(self) -> None:
        self._listings: dict[str, frozenset[str]] = {}
        self._folders: dict[str, tuple[bool, str | None]] = {}  # key -> (exists, blocker)

    def names(self, directory: Path) -> frozenset[str]:
        """Casefolded names in ``directory``; empty if it does not exist yet."""
        key = path_key(directory)
        if key not in self._listings:
            try:
                self._listings[key] = frozenset(n.casefold() for n in os.listdir(directory))
            except (FileNotFoundError, NotADirectoryError):
                self._listings[key] = frozenset()
        return self._listings[key]

    def _folder_state(self, folder: Path) -> tuple[bool, str | None]:
        key = path_key(folder)
        if key not in self._folders:
            if not os.path.lexists(folder):
                self._folders[key] = (False, None)
            elif os.path.isdir(folder):
                self._folders[key] = (True, None)
            else:
                self._folders[key] = (True, f"'{folder}' exists but is not a folder")
        return self._folders[key]

    def blocker(self, parent: Path, destination: Path) -> str | None:
        """Return a message if a folder this plan needs is occupied by a file."""
        chain = [parent]
        while not same_path(chain[-1], destination) and chain[-1].parent != chain[-1]:
            chain.append(chain[-1].parent)
        for folder in reversed(chain):  # from the destination downwards
            exists, problem = self._folder_state(folder)
            if problem:
                return problem
            if not exists:
                return None  # nothing deeper can exist yet
        return None


def _sort_key(item: ScannedFile) -> tuple[str, str]:
    return (str(item.path).casefold(), str(item.path))


def build_plan(
    scan: ScanResult,
    rules: ClassificationRules,
    destination: str | os.PathLike[str],
    options: PlanOptions | None = None,
) -> Plan:
    """Turn a scan into a deterministic, preview-only plan.

    The same scan, rules, destination and options always give the same plan,
    in the same order, with the same conflict resolutions.
    """
    options = options or PlanOptions()
    validation = validate_paths(scan.source, destination)
    if not validation.ok:
        raise PlanValidationError(validation.errors)

    destination_path = Path(os.path.abspath(destination))
    disk = _DiskView()
    claimed: set[str] = set()  # casefolded target keys already used by this plan
    items: list[PlannedOperation] = []

    def claim_key(path: Path) -> str:
        return path_key(path).casefold()

    for index, file in enumerate(sorted(scan.files, key=_sort_key)):
        classification = rules.classify(file.name)
        parts: tuple[str, ...] = (classification.folder,)
        if options.layout is Layout.PRESERVE_STRUCTURE:
            parts += sanitize_relative_parts(file.relative_dir)
        target_dir = destination_path.joinpath(*parts)
        desired = target_dir / file.name

        def make(status: Status, target: Path | None, conflict: ConflictKind, message: str = "") -> PlannedOperation:
            return PlannedOperation(
                index=index,
                source=file.path,
                desired_target=desired,
                target=target,
                action=options.action,
                category=classification.category,
                folder=classification.folder,
                extension=classification.extension,
                classification_reason=classification.reason,
                size=file.size,
                mtime_ns=file.mtime_ns,
                conflict=conflict,
                status=status,
                message=message,
            )

        blocker = disk.blocker(target_dir, destination_path)
        if blocker:
            items.append(make(Status.BLOCKED, None, ConflictKind.NONE, f"Destination folder unavailable: {blocker}."))
            continue
        try:
            on_disk = disk.names(target_dir)
        except OSError as exc:
            items.append(make(Status.BLOCKED, None, ConflictKind.NONE, f"Cannot read destination folder: {exc}."))
            continue

        def is_taken(name: str) -> bool:
            return name.casefold() in on_disk or claim_key(target_dir / name) in claimed

        if not is_taken(file.name):
            if len(str(desired)) > options.max_path_length:
                items.append(make(Status.BLOCKED, None, ConflictKind.NONE,
                                  f"Target path is {len(str(desired))} characters; the limit is {options.max_path_length}."))
                continue
            claimed.add(claim_key(desired))
            items.append(make(Status.READY, desired, ConflictKind.NONE))
            continue

        kind = (
            ConflictKind.EXISTS_ON_DISK
            if file.name.casefold() in on_disk
            else ConflictKind.DUPLICATE_IN_PLAN
        )
        reason = (
            f"A file named '{file.name}' already exists in '{target_dir}'."
            if kind is ConflictKind.EXISTS_ON_DISK
            else f"Another file in this plan is also headed to '{target_dir / file.name}'."
        )
        if options.conflict_policy is ConflictPolicy.SKIP:
            items.append(make(Status.SKIPPED, None, kind, f"Skipped. {reason}"))
            continue

        for number in range(1, MAX_RENAME_ATTEMPTS + 1):
            new_name = rename_candidate(file.name, classification.extension, number)
            if not is_taken(new_name):
                break
        else:
            items.append(make(Status.BLOCKED, None, kind, f"No free name found for '{file.name}'."))
            continue
        renamed = target_dir / new_name
        if len(str(renamed)) > options.max_path_length:
            items.append(make(Status.BLOCKED, None, kind,
                              f"Renamed target path is {len(str(renamed))} characters; the limit is {options.max_path_length}."))
            continue
        claimed.add(claim_key(renamed))
        items.append(make(Status.RENAMED, renamed, kind, f"Renamed to '{new_name}'. {reason}"))

    return Plan(
        source=scan.source,
        destination=destination_path,
        options=options,
        items=tuple(items),
        warnings=validation.warnings,
    )


def extension_summary(scan: ScanResult, rules: ClassificationRules) -> list[ExtensionSummary]:
    """One row per detected extension: count, size, suggested category and folder.

    Keyword rules are per-file and are not reflected here; they appear in the
    plan itself.
    """
    counts: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    for file in scan.files:
        counts[file.extension] += 1
        sizes[file.extension] += file.size
    rows = []
    for extension, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        classification = rules.classify_extension(extension)
        rows.append(
            ExtensionSummary(
                extension=extension,
                label=extension or NO_EXTENSION_LABEL,
                count=count,
                total_size=sizes[extension],
                category=classification.category,
                folder=classification.folder,
            )
        )
    return rows
