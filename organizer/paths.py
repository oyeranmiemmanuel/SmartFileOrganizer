"""Path helpers shared by the classification, scanning and planning layers.

Everything here is a pure function over strings and paths. No function in this
module creates, changes or deletes anything on disk.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

# Characters Windows does not allow in file or folder names, plus control characters.
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Device names Windows reserves, with or without an extension (for example "CON.txt").
RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

MAX_FOLDER_NAME_LENGTH = 100
FALLBACK_NAME = "_"


def sanitize_name(
    name: str,
    fallback: str = FALLBACK_NAME,
    max_length: int = MAX_FOLDER_NAME_LENGTH,
) -> str:
    """Return a single safe path component derived from ``name``.

    * Invalid characters (including ``/`` and ``\\``) become ``_``, so a name can
      never introduce extra path levels or escape its parent folder.
    * Leading/trailing spaces and trailing dots are removed (Windows drops them).
    * ``.``, ``..`` and empty results become ``fallback``.
    * Reserved Windows device names get a ``_`` prefix.
    * The result is truncated to ``max_length`` characters.
    """
    cleaned = _INVALID_CHARS.sub("_", str(name)).strip().rstrip(". ")
    if cleaned.split(".")[0].rstrip(" ").upper() in RESERVED_NAMES:
        cleaned = "_" + cleaned
    cleaned = cleaned[:max_length].rstrip(". ")
    return cleaned or fallback


def sanitize_relative_parts(parts: Iterable[str]) -> tuple[str, ...]:
    """Sanitize each component of a relative folder path.

    Used when the original folder structure is preserved in the destination.
    Names that are already valid pass through unchanged.
    """
    return tuple(sanitize_name(part, max_length=255) for part in parts)


def path_key(path: str | os.PathLike[str]) -> str:
    """Absolute, case-normalized (on Windows) string used to compare paths."""
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def same_path(a: str | os.PathLike[str], b: str | os.PathLike[str]) -> bool:
    return path_key(a) == path_key(b)


def is_within(child: str | os.PathLike[str], parent: str | os.PathLike[str]) -> bool:
    """True if ``child`` is located strictly inside ``parent``."""
    child_key, parent_key = path_key(child), path_key(parent)
    if child_key == parent_key:
        return False
    try:
        return os.path.commonpath([child_key, parent_key]) == parent_key
    except ValueError:  # different drives, or mixed absolute/relative paths
        return False


def default_destination(source: str | os.PathLike[str]) -> Path:
    """Default destination: a sibling folder named ``<source>_Organized``."""
    src = Path(os.path.abspath(os.fspath(source)))
    if not src.name:  # drive root such as C:\; validation will reject the result
        return src / "Organized"
    return src.parent / f"{src.name}_Organized"