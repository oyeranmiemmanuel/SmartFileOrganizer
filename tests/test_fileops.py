import errno
import os

import pytest

from organizer import fileops
from organizer.fileops import (
    claim_target,
    copy_file,
    create_exclusive,
    move_file,
    release_claim,
)
from organizer.planner import ConflictPolicy
from tests.helpers import make_tree


def test_create_exclusive_never_replaces_anything(tmp_path):
    assert create_exclusive(tmp_path / "new.txt")
    (tmp_path / "taken.txt").write_bytes(b"keep")
    assert not create_exclusive(tmp_path / "taken.txt")
    assert (tmp_path / "taken.txt").read_bytes() == b"keep"
    (tmp_path / "folder").mkdir()
    assert not create_exclusive(tmp_path / "folder")


def test_claim_target_free_name(tmp_path):
    claimed = claim_target(tmp_path / "a.jpg", ConflictPolicy.RENAME, ".jpg")
    assert claimed == tmp_path / "a.jpg" and claimed.exists()


def test_claim_target_rename_numbers_past_existing_names(tmp_path):
    make_tree(tmp_path, {"a.jpg": b"1", "a (1).jpg": b"2"})
    claimed = claim_target(tmp_path / "a.jpg", ConflictPolicy.RENAME, ".jpg")
    assert claimed.name == "a (2).jpg"
    assert (tmp_path / "a.jpg").read_bytes() == b"1"


def test_claim_target_skip_policy_returns_none(tmp_path):
    make_tree(tmp_path, {"a.jpg": b"1"})
    assert claim_target(tmp_path / "a.jpg", ConflictPolicy.SKIP, ".jpg") is None
    assert [p.name for p in tmp_path.iterdir()] == ["a.jpg"]


def test_copy_file_copies_content_and_mtime(tmp_path):
    src, dst = tmp_path / "src.bin", tmp_path / "dst.bin"
    src.write_bytes(os.urandom(3 * 1024 * 1024 + 17))
    os.utime(src, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
    create_exclusive(dst)
    copy_file(src, dst)
    assert dst.read_bytes() == src.read_bytes()
    assert dst.stat().st_mtime_ns == src.stat().st_mtime_ns


def test_copy_file_detects_size_mismatch(tmp_path, monkeypatch):
    src, dst = tmp_path / "s", tmp_path / "d"
    src.write_bytes(b"abcdef")
    create_exclusive(dst)
    monkeypatch.setattr(fileops.shutil, "copyfileobj", lambda r, w, n: w.write(b"abc"))
    with pytest.raises(fileops.VerificationError):
        copy_file(src, dst)


def test_move_file_same_volume_is_a_rename(tmp_path):
    src, dst = tmp_path / "s", tmp_path / "d"
    src.write_bytes(b"data")
    create_exclusive(dst)
    assert move_file(src, dst) == "rename"
    assert not src.exists() and dst.read_bytes() == b"data"


def _force_cross_device(monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(fileops.os, "replace", refuse)


def test_move_file_falls_back_to_copy_and_delete_across_drives(tmp_path, monkeypatch):
    src, dst = tmp_path / "s", tmp_path / "d"
    src.write_bytes(b"payload")
    os.utime(src, ns=(1_500_000_000_000_000_000,) * 2)
    create_exclusive(dst)
    _force_cross_device(monkeypatch)
    assert move_file(src, dst) == "copy-delete"
    assert not src.exists()
    assert dst.read_bytes() == b"payload"
    assert dst.stat().st_mtime_ns == 1_500_000_000_000_000_000


def test_cross_drive_move_keeps_source_if_it_cannot_be_deleted(tmp_path, monkeypatch):
    src, dst = tmp_path / "s", tmp_path / "d"
    src.write_bytes(b"payload")
    create_exclusive(dst)
    _force_cross_device(monkeypatch)

    def locked(path):
        raise PermissionError("in use")

    monkeypatch.setattr(fileops, "_remove_source", locked)
    with pytest.raises(PermissionError):
        move_file(src, dst)
    assert src.read_bytes() == b"payload"  # source untouched
    release_claim(src, dst)
    assert not dst.exists()  # the half-finished copy is cleaned up


def test_other_replace_errors_are_not_treated_as_cross_device(tmp_path, monkeypatch):
    src, dst = tmp_path / "s", tmp_path / "d"
    src.write_bytes(b"x")
    create_exclusive(dst)
    monkeypatch.setattr(fileops.os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError("denied")))
    with pytest.raises(PermissionError):
        move_file(src, dst)
    assert src.exists()


def test_release_claim_never_deletes_a_file_that_was_already_moved(tmp_path):
    src, dst = tmp_path / "s", tmp_path / "d"
    src.write_bytes(b"data")
    create_exclusive(dst)
    move_file(src, dst)  # source is gone, dst holds the data
    release_claim(src, dst)
    assert dst.read_bytes() == b"data"


def test_is_link_detects_symlinks(tmp_path):
    (tmp_path / "real").write_bytes(b"x")
    try:
        (tmp_path / "link").symlink_to(tmp_path / "real")
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available in this environment")
    assert fileops.is_link(tmp_path / "link")
    assert not fileops.is_link(tmp_path / "real")
    assert not fileops.is_link(tmp_path / "missing")
