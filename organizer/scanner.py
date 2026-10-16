"""Read-only directory scanning.

``scan_directory`` only lists directories and reads file metadata. It never
creates, moves, copies, renames or deletes anything, and it never opens files.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .categories import ClassificationRules, default_rules
from .paths import path_key

# Directories skipped during recursive scans (compared case-insensitively).
DEFAULT_EXCLUDED_DIR_NAMES: tuple[str, ...] = (
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    ".idea", ".vscode", "$RECYCLE.BIN", "System Volume Information",
)

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_REPARSE_POINT = 0x400  # symlinks and junctions on Windows

# Reasons an entry was skipped.
SKIP_HIDDEN = "hidden"
SKIP_SYSTEM = "system"
SKIP_LINK = "link"
SKIP_EXCLUDED_DIR = "excluded_directory"
SKIP_EXCLUDED_PATH = "excluded_path"
SKIP_NOT_REGULAR = "not_a_regular_file"


@dataclass(frozen=True)
class ScannedFile:
    path: Path
    relative_dir: tuple[str, ...]  # folders between the source root and the file
    name: str
    extension: str  # lowercase with leading dot, "" if none
    size: int
    mtime_ns: int

    @property
    def relative_path(self) -> Path:
        return Path(*self.relative_dir, self.name)


@dataclass(frozen=True)
class SkippedEntry:
    path: Path
    reason: str


@dataclass(frozen=True)
class ScanError:
    path: Path
    message: str


@dataclass(frozen=True)
class ScanProgress:
    files_found: int
    directories_scanned: int
    current_directory: Path


@dataclass
class ScanResult:
    source: Path
    recursive: bool
    include_hidden: bool
    files: list[ScannedFile] = field(default_factory=list)
    skipped: list[SkippedEntry] = field(default_factory=list)
    errors: list[ScanError] = field(default_factory=list)
    directories_scanned: int = 0
    cancelled: bool = False

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)

    def extension_counts(self) -> dict[str, int]:
        """Files per extension ("" = no extension), most common first."""
        counts = Counter(f.extension for f in self.files)
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _attributes(stat_result: os.stat_result) -> int:
    return getattr(stat_result, "st_file_attributes", 0)  # Windows only


def scan_directory(
    source: str | os.PathLike[str],
    *,
    recursive: bool = False,
    rules: ClassificationRules | None = None,
    excluded_dir_names: Iterable[str] = DEFAULT_EXCLUDED_DIR_NAMES,
    exclude_paths: Iterable[str | os.PathLike[str]] = (),
    include_hidden: bool = False,
    progress: Callable[[ScanProgress], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    progress_interval: int = 200,
) -> ScanResult:
    """List the regular files under ``source``.

    * Non-recursive scans look at the top level only.
    * Symbolic links and Windows junctions are never followed.
    * Entries with the Windows SYSTEM attribute are always skipped. Hidden
      entries (dot-names or the Windows HIDDEN attribute) are skipped unless
      ``include_hidden`` is true.
    * Directories named in ``excluded_dir_names`` and the paths in
      ``exclude_paths`` (for example the destination) are not entered.
    * Unreadable entries are recorded in ``errors``; the scan continues.
    * ``progress`` is called every ``progress_interval`` files and once at the
      end. ``should_cancel`` is polled between entries; a cancelled scan
      returns the partial result with ``cancelled=True``.

    Results are deterministic: directories and entries are visited in
    case-insensitive name order.
    """
    source_path = Path(source)
    if not source_path.is_dir():
        raise NotADirectoryError(f"Source is not a folder: {source_path}")

    rules = rules or default_rules()
    excluded_names = {name.casefold() for name in excluded_dir_names}
    excluded_keys = {path_key(p) for p in exclude_paths}
    result = ScanResult(source=source_path, recursive=recursive, include_hidden=include_hidden)
    next_report = progress_interval

    def report(directory: Path) -> None:
        if progress:
            progress(ScanProgress(len(result.files), result.directories_scanned, directory))

    stack: list[tuple[Path, tuple[str, ...]]] = [(source_path, ())]
    while stack:
        directory, relative = stack.pop()
        if should_cancel and should_cancel():
            result.cancelled = True
            break
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda e: (e.name.casefold(), e.name))
        except OSError as exc:
            result.errors.append(ScanError(directory, f"Cannot read folder: {exc}"))
            continue
        result.directories_scanned += 1

        subdirectories: list[tuple[Path, tuple[str, ...]]] = []
        for entry in entries:
            if should_cancel and should_cancel():
                result.cancelled = True
                break
            path = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
                is_link = entry.is_symlink()
                is_dir = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError as exc:
                result.errors.append(ScanError(path, f"Cannot read entry: {exc}"))
                continue
            attributes = _attributes(info)

            if is_link:
                result.skipped.append(SkippedEntry(path, SKIP_LINK))
                continue

            if is_dir:
                if not recursive:
                    continue  # subfolders are simply not part of a top-level scan
                if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                    result.skipped.append(SkippedEntry(path, SKIP_LINK))
                elif attributes & FILE_ATTRIBUTE_SYSTEM:
                    result.skipped.append(SkippedEntry(path, SKIP_SYSTEM))
                elif entry.name.casefold() in excluded_names:
                    result.skipped.append(SkippedEntry(path, SKIP_EXCLUDED_DIR))
                elif path_key(path) in excluded_keys:
                    result.skipped.append(SkippedEntry(path, SKIP_EXCLUDED_PATH))
                elif not include_hidden and (
                    entry.name.startswith(".") or attributes & FILE_ATTRIBUTE_HIDDEN
                ):
                    result.skipped.append(SkippedEntry(path, SKIP_HIDDEN))
                else:
                    subdirectories.append((path, relative + (entry.name,)))
                continue

            if not is_file:
                result.skipped.append(SkippedEntry(path, SKIP_NOT_REGULAR))
            elif attributes & FILE_ATTRIBUTE_SYSTEM:
                result.skipped.append(SkippedEntry(path, SKIP_SYSTEM))
            elif not include_hidden and (
                entry.name.startswith(".") or attributes & FILE_ATTRIBUTE_HIDDEN
            ):
                result.skipped.append(SkippedEntry(path, SKIP_HIDDEN))
            else:
                result.files.append(
                    ScannedFile(
                        path=path,
                        relative_dir=relative,
                        name=entry.name,
                        extension=rules.extension_of(entry.name),
                        size=info.st_size,
                        mtime_ns=info.st_mtime_ns,
                    )
                )
                if progress and len(result.files) >= next_report:
                    report(directory)
                    next_report = len(result.files) + progress_interval

        if result.cancelled:
            break
        stack.extend(reversed(subdirectories))  # visit subfolders in name order

    report(source_path)
    return result