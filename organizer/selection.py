"""Choosing what takes part in an operation: whole file types, or individual files."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, NamedTuple

from .paths import path_key
from .scanner import ScannedFile, ScanResult


@dataclass(frozen=True)
class Selection:
    """Either whole file types (``extensions``) or an explicit set of files (``files``).

    ``files`` holds ``paths.path_key`` values. When it is not None it takes
    over and ``extensions`` is ignored.
    """

    extensions: frozenset[str] = frozenset()
    files: frozenset[str] | None = None

    @property
    def by_files(self) -> bool:
        return self.files is not None


class SelectionSummary(NamedTuple):
    files: int
    size: int
    extensions: int  # distinct extensions among the chosen files
    total_extensions: int


def file_key(item: ScannedFile) -> str:
    return path_key(item.path)


def as_selection(value: Selection | Iterable[str]) -> Selection:
    """Accept a Selection, or a plain collection of extensions (the older form)."""
    if isinstance(value, Selection):
        return value
    return Selection(extensions=frozenset(value))


def all_extensions(scan: ScanResult) -> set[str]:
    """Every extension found in the scan ("" stands for files without one)."""
    return {item.extension for item in scan.files}


def _chosen(scan: ScanResult, selection: Selection) -> list[ScannedFile]:
    if selection.files is not None:
        return [item for item in scan.files if file_key(item) in selection.files]
    return [item for item in scan.files if item.extension in selection.extensions]


def filter_scan(scan: ScanResult, selected: Selection | Iterable[str]) -> ScanResult:
    """A copy of ``scan`` holding only the chosen files. The original is not changed."""
    return replace(scan, files=_chosen(scan, as_selection(selected)))


def summarize_selection(scan: ScanResult, selected: Selection | Iterable[str]) -> SelectionSummary:
    chosen = _chosen(scan, as_selection(selected))
    return SelectionSummary(
        files=len(chosen),
        size=sum(item.size for item in chosen),
        extensions=len({item.extension for item in chosen}),
        total_extensions=len(all_extensions(scan)),
    )