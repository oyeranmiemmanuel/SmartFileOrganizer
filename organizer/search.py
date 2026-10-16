"""Searching a scan for individual files that match criteria.

Pure functions: nothing here touches the disk or changes any file. All the
criteria are optional and combined with AND.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .categories import ClassificationRules
from .paths import path_key
from .scanner import ScannedFile, ScanResult

# label shown in the interface -> internal mode
MATCH_MODES = {
    "Contains": "contains",
    "Starts with": "starts",
    "Ends with": "ends",
    "Wildcard (* ?)": "wildcard",
}
SIZE_UNITS = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}

_TOKEN_SPLIT = re.compile(r"[,;\s]+")
_TOKEN = re.compile(r"^\.?[a-z0-9][a-z0-9_+~.\-]{0,31}$")


class SearchError(ValueError):
    """The search criteria are not valid. The message is meant for the user."""


@dataclass(frozen=True)
class SearchCriteria:
    text: str = ""
    match: str = "contains"
    extensions: frozenset[str] | None = None  # None = any; "" stands for no extension
    category: str | None = None
    min_size: int | None = None  # bytes, inclusive
    max_size: int | None = None  # bytes, inclusive
    modified_from_ns: int | None = None  # inclusive
    modified_before_ns: int | None = None  # exclusive
    folder_text: str = ""

    @property
    def is_empty(self) -> bool:
        return (
            not self.text.strip()
            and self.extensions is None
            and self.category is None
            and self.min_size is None
            and self.max_size is None
            and self.modified_from_ns is None
            and self.modified_before_ns is None
            and not self.folder_text.strip()
        )


@dataclass(frozen=True)
class SearchHit:
    file: ScannedFile
    key: str  # paths.path_key(file.path): the identity used for selections
    category: str


def parse_extensions(text: str) -> frozenset[str] | None:
    """'jpg, .PNG tar.gz none' -> {'.jpg', '.png', '.tar.gz', ''}. Empty text means any type."""
    tokens = [token for token in _TOKEN_SPLIT.split(text.strip().lower()) if token]
    if not tokens:
        return None
    result: set[str] = set()
    for token in tokens:
        if token in ("none", "-"):
            result.add("")
            continue
        if not _TOKEN.match(token):
            raise SearchError(f"'{token}' is not a valid file type. Use names like jpg, .png or tar.gz.")
        result.add(token if token.startswith(".") else "." + token)
    return frozenset(result)


def parse_size(text: str, unit: str = "MB") -> int | None:
    """'1.5' with 'MB' -> bytes. Empty text means no limit."""
    cleaned = text.strip()
    if not cleaned:
        return None
    if unit not in SIZE_UNITS:
        raise SearchError(f"Unknown size unit: {unit}")
    try:
        value = float(cleaned)
    except ValueError:
        raise SearchError(f"'{cleaned}' is not a number. Use digits such as 2 or 0.5.") from None
    if value != value or value < 0 or value == float("inf"):
        raise SearchError("Sizes must be zero or more.")
    return int(value * SIZE_UNITS[unit])


def parse_day(text: str) -> date | None:
    """'2024-03-31' -> a date. Empty text means no limit."""
    cleaned = text.strip().replace("/", "-")
    if not cleaned:
        return None
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date()
    except ValueError:
        raise SearchError("Dates must look like 2024-03-31 (year-month-day).") from None


def _day_start_ns(day: date) -> int:
    try:
        return int(datetime(day.year, day.month, day.day).timestamp()) * 1_000_000_000
    except (OverflowError, OSError, ValueError):
        raise SearchError("That date is outside the range this computer can handle.") from None


def build_criteria(
    *,
    text: str = "",
    match: str = "contains",
    extensions_text: str = "",
    category: str | None = None,
    min_size_text: str = "",
    max_size_text: str = "",
    size_unit: str = "MB",
    modified_from_text: str = "",
    modified_to_text: str = "",
    folder_text: str = "",
) -> SearchCriteria:
    """Turn the text typed into the search form into validated criteria."""
    if match not in MATCH_MODES.values():
        raise SearchError(f"Unknown name match mode: {match}")
    min_size = parse_size(min_size_text, size_unit)
    max_size = parse_size(max_size_text, size_unit)
    if min_size is not None and max_size is not None and min_size > max_size:
        raise SearchError("The smallest size is larger than the largest size.")

    first = parse_day(modified_from_text)
    last = parse_day(modified_to_text)
    if first is not None and last is not None and first > last:
        raise SearchError("The 'modified from' date is after the 'modified to' date.")
    from_ns = _day_start_ns(first) if first is not None else None
    before_ns = None
    if last is not None:
        try:
            before_ns = _day_start_ns(last + timedelta(days=1))  # the end date itself is included
        except OverflowError:
            raise SearchError("That date is outside the range this computer can handle.") from None

    return SearchCriteria(
        text=text.strip(),
        match=match,
        extensions=parse_extensions(extensions_text),
        category=category or None,
        min_size=min_size,
        max_size=max_size,
        modified_from_ns=from_ns,
        modified_before_ns=before_ns,
        folder_text=folder_text.strip(),
    )


def name_matches(name: str, text: str, mode: str) -> bool:
    """Case-insensitive file name test. Wildcard text without * ? [ is treated as 'contains'."""
    haystack, needle = name.casefold(), text.casefold()
    if mode == "starts":
        return haystack.startswith(needle)
    if mode == "ends":
        return haystack.endswith(needle)
    if mode == "wildcard" and any(char in needle for char in "*?["):
        return fnmatch.fnmatchcase(haystack, needle)
    return needle in haystack


def find_files(scan: ScanResult, criteria: SearchCriteria, rules: ClassificationRules) -> list[SearchHit]:
    """Files of ``scan`` that match every criterion, in scan order."""
    needle = criteria.text.strip()
    folder_needle = criteria.folder_text.strip().casefold()
    hits: list[SearchHit] = []
    for item in scan.files:
        if criteria.extensions is not None and item.extension not in criteria.extensions:
            continue
        if criteria.min_size is not None and item.size < criteria.min_size:
            continue
        if criteria.max_size is not None and item.size > criteria.max_size:
            continue
        if criteria.modified_from_ns is not None and item.mtime_ns < criteria.modified_from_ns:
            continue
        if criteria.modified_before_ns is not None and item.mtime_ns >= criteria.modified_before_ns:
            continue
        if needle and not name_matches(item.name, needle, criteria.match):
            continue
        if folder_needle and folder_needle not in "/".join(item.relative_dir).casefold():
            continue
        category = rules.classify(item.name).category
        if criteria.category is not None and category != criteria.category:
            continue
        hits.append(SearchHit(item, path_key(item.path), category))
    return hits


def format_mtime(mtime_ns: int) -> str:
    """'2024-03-31 14:05' in local time."""
    try:
        return datetime.fromtimestamp(mtime_ns / 1_000_000_000).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return "unknown"