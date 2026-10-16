"""Low-level, no-overwrite file operations.

These are the only functions in the project that change files. They are small
on purpose so that the safety rules can be read and tested in one place:

* A target name is *claimed* by exclusively creating an empty file there
  (``O_CREAT | O_EXCL``). The operating system guarantees only one claimant
  wins, so an existing file can never be overwritten, even if it appeared
  after the preview was built.
* Only a claim this program created may be replaced or removed.
* A move is one atomic rename where possible. Across drives it is
  copy, verify size, then delete the source: the source is deleted only after
  the copy is complete and verified.
"""

from __future__ import annotations

import errno
import os
import shutil
import stat
from pathlib import Path

from .planner import MAX_RENAME_ATTEMPTS, ConflictPolicy, rename_candidate

COPY_CHUNK = 1024 * 1024
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_WINERROR_NOT_SAME_DEVICE = 17


class VerificationError(OSError):
    """A copied file did not match its source."""


def is_link(path: str | os.PathLike[str]) -> bool:
    """True for symlinks and Windows junctions/reparse points (without following)."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def create_exclusive(path: str | os.PathLike[str]) -> bool:
    """Create an empty file at ``path``. False if anything already exists there."""
    if os.path.lexists(path):  # also covers folders, which O_EXCL reports poorly on Windows
        return False
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    try:
        os.close(os.open(path, flags, 0o666))
    except FileExistsError:
        return False
    return True


def claim_target(
    desired: Path,
    policy: ConflictPolicy,
    extension: str = "",
) -> Path | None:
    """Claim a free file name at or near ``desired``.

    Returns the claimed path (now an empty placeholder owned by the caller), or
    ``None`` if the name is taken and ``policy`` is SKIP. With RENAME, numbered
    names ("name (1).ext") are tried in order.
    """
    if create_exclusive(desired):
        return desired
    if policy is ConflictPolicy.SKIP:
        return None
    for number in range(1, MAX_RENAME_ATTEMPTS + 1):
        candidate = desired.with_name(rename_candidate(desired.name, extension, number))
        if create_exclusive(candidate):
            return candidate
    raise FileExistsError(errno.EEXIST, f"No free name found for '{desired.name}'", str(desired))


def release_claim(source: str | os.PathLike[str], claimed: str | os.PathLike[str]) -> None:
    """Remove a claimed placeholder after a failed operation.

    Refuses unless ``source`` still exists, so a file that was already moved
    into ``claimed`` is never deleted.
    """
    if os.path.lexists(source):
        try:
            os.unlink(claimed)
        except FileNotFoundError:
            pass


def _is_cross_device(exc: OSError) -> bool:
    return exc.errno == errno.EXDEV or getattr(exc, "winerror", None) == _WINERROR_NOT_SAME_DEVICE


def copy_file(source: str | os.PathLike[str], claimed: str | os.PathLike[str]) -> None:
    """Copy ``source`` into the claimed placeholder, preserving timestamps.

    Raises ``VerificationError`` if the copy's size differs from the source.
    The caller removes the placeholder on any exception.
    """
    with open(source, "rb") as reader, open(claimed, "wb") as writer:
        shutil.copyfileobj(reader, writer, COPY_CHUNK)
        writer.flush()
        os.fsync(writer.fileno())
    try:
        shutil.copystat(source, claimed)
    except OSError:
        pass  # some file systems reject metadata; the data itself is already safe
    if os.path.getsize(source) != os.path.getsize(claimed):
        raise VerificationError(errno.EIO, "Copied file size does not match the source", str(claimed))


def _remove_source(source: str | os.PathLike[str]) -> None:
    try:
        os.unlink(source)
    except PermissionError:
        mode = os.stat(source).st_mode
        os.chmod(source, mode | stat.S_IWRITE)  # clears the Windows read-only attribute
        try:
            os.unlink(source)
        except OSError:
            os.chmod(source, mode)
            raise


def move_file(source: str | os.PathLike[str], claimed: str | os.PathLike[str]) -> str:
    """Move ``source`` onto the claimed placeholder. Returns "rename" or "copy-delete".

    The caller removes the placeholder on any exception. When this raises, the
    source file is still in place.
    """
    try:
        os.replace(source, claimed)  # replaces only our own empty placeholder
        return "rename"
    except OSError as exc:
        if not _is_cross_device(exc):
            raise
    copy_file(source, claimed)
    _remove_source(source)
    return "copy-delete"
