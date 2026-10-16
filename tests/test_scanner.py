import os
from pathlib import Path

import pytest

from organizer import scanner
from organizer.scanner import (
    SKIP_EXCLUDED_DIR,
    SKIP_EXCLUDED_PATH,
    SKIP_HIDDEN,
    SKIP_LINK,
    scan_directory,
)
from tests.helpers import make_tree, snapshot


def names(result):
    return sorted(f.relative_path.as_posix() for f in result.files)


def test_non_recursive_scan_sees_top_level_files_only(tmp_path):
    make_tree(tmp_path, ["a.txt", "b.jpg", "sub/c.png", "sub/deep/d.pdf"])
    result = scan_directory(tmp_path)
    assert names(result) == ["a.txt", "b.jpg"]
    assert not result.recursive
    assert result.skipped == [] and result.errors == []


def test_recursive_scan_records_relative_folders(tmp_path):
    make_tree(tmp_path, ["a.txt", "sub/c.png", "sub/deep/d.pdf"])
    result = scan_directory(tmp_path, recursive=True)
    assert names(result) == ["a.txt", "sub/c.png", "sub/deep/d.pdf"]
    deep = next(f for f in result.files if f.name == "d.pdf")
    assert deep.relative_dir == ("sub", "deep")
    assert deep.path == tmp_path / "sub" / "deep" / "d.pdf"
    assert result.directories_scanned == 3


def test_extension_counts_and_sizes(tmp_path):
    make_tree(
        tmp_path,
        {"a.JPG": b"1234", "b.jpg": b"12", "c.png": b"1", "README": b"", "x.tar.gz": b"123"},
    )
    result = scan_directory(tmp_path)
    assert result.extension_counts() == {".jpg": 2, "": 1, ".png": 1, ".tar.gz": 1}
    assert result.total_size == 10
    jpg = next(f for f in result.files if f.name == "a.JPG")
    assert (jpg.extension, jpg.size) == (".jpg", 4)


@pytest.mark.parametrize("excluded", [".git", "node_modules", "$RECYCLE.BIN", "NODE_MODULES", ".Git"])
def test_default_excluded_directories_are_not_entered(tmp_path, excluded):
    make_tree(tmp_path, ["keep.txt", f"{excluded}/inner.txt", f"{excluded}/deeper/more.txt"])
    result = scan_directory(tmp_path, recursive=True)
    assert names(result) == ["keep.txt"]
    assert [(s.path.name, s.reason) for s in result.skipped] == [(excluded, SKIP_EXCLUDED_DIR)]


def test_excluded_directory_names_are_configurable(tmp_path):
    make_tree(tmp_path, ["keep.txt", "skipme/a.txt", ".git/b.txt"])
    result = scan_directory(
        tmp_path, recursive=True, excluded_dir_names=["skipme"], include_hidden=True
    )
    # Only the configured name is excluded now; ".git" is no longer in the list.
    assert names(result) == [".git/b.txt", "keep.txt"]


def test_hidden_entries_skipped_by_default_and_includable(tmp_path):
    make_tree(tmp_path, ["visible.txt", ".hidden.txt", ".hiddendir/inner.txt"])
    default = scan_directory(tmp_path, recursive=True)
    assert names(default) == ["visible.txt"]
    assert {s.reason for s in default.skipped} == {SKIP_HIDDEN}
    included = scan_directory(tmp_path, recursive=True, include_hidden=True)
    assert names(included) == [".hidden.txt", ".hiddendir/inner.txt", "visible.txt"]


def test_system_attribute_entries_are_always_skipped(tmp_path, monkeypatch):
    make_tree(tmp_path, ["normal.txt", "desktop.ini", "Sys/inner.txt"])

    class Wrapped:  # simulate Windows file attributes on a Linux file system
        def __init__(self, entry):
            self._entry = entry

        def __getattr__(self, item):
            return getattr(self._entry, item)

        def stat(self, *, follow_symlinks=True):
            info = self._entry.stat(follow_symlinks=follow_symlinks)
            attributes = scanner.FILE_ATTRIBUTE_SYSTEM if self._entry.name in ("desktop.ini", "Sys") else 0
            return type("S", (), {
                "st_size": info.st_size,
                "st_mtime_ns": info.st_mtime_ns,
                "st_file_attributes": attributes,
            })()

    real_scandir = os.scandir

    class Scandir:
        def __init__(self, path):
            self._inner = real_scandir(path)

        def __enter__(self):
            return (Wrapped(e) for e in self._inner.__enter__())

        def __exit__(self, *exc):
            return self._inner.__exit__(*exc)

    monkeypatch.setattr(scanner.os, "scandir", Scandir)
    result = scan_directory(tmp_path, recursive=True, include_hidden=True)
    assert names(result) == ["normal.txt"]
    assert {s.path.name for s in result.skipped} == {"desktop.ini", "Sys"}


def test_exclude_paths_keeps_destination_out_of_the_scan(tmp_path):
    make_tree(tmp_path, ["a.txt", "Organized/Images/b.jpg"])
    result = scan_directory(tmp_path, recursive=True, exclude_paths=[tmp_path / "Organized"])
    assert names(result) == ["a.txt"]
    assert [s.reason for s in result.skipped] == [SKIP_EXCLUDED_PATH]


def test_symlinks_are_not_followed(tmp_path):
    outside = tmp_path / "outside"
    source = tmp_path / "source"
    make_tree(outside, ["secret.txt"])
    make_tree(source, ["real.txt"])
    try:
        (source / "dirlink").symlink_to(outside, target_is_directory=True)
        (source / "filelink.txt").symlink_to(outside / "secret.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available in this environment")
    result = scan_directory(source, recursive=True)
    assert names(result) == ["real.txt"]
    assert {s.reason for s in result.skipped} == {SKIP_LINK}


def test_unreadable_folder_is_reported_and_scan_continues(tmp_path, monkeypatch):
    make_tree(tmp_path, ["a.txt", "locked/b.txt", "open/c.txt"])
    real_scandir = os.scandir

    def flaky(path):
        if Path(path).name == "locked":
            raise PermissionError("access denied")
        return real_scandir(path)

    monkeypatch.setattr(scanner.os, "scandir", flaky)
    result = scan_directory(tmp_path, recursive=True)
    assert names(result) == ["a.txt", "open/c.txt"]
    assert len(result.errors) == 1 and result.errors[0].path.name == "locked"
    assert "access denied" in result.errors[0].message


def test_missing_source_raises(tmp_path):
    with pytest.raises(NotADirectoryError):
        scan_directory(tmp_path / "does-not-exist")
    make_tree(tmp_path, ["file.txt"])
    with pytest.raises(NotADirectoryError):
        scan_directory(tmp_path / "file.txt")


def test_progress_callback_and_cancellation(tmp_path):
    make_tree(tmp_path, [f"f{i:03}.txt" for i in range(50)])
    updates = []
    result = scan_directory(tmp_path, progress=updates.append, progress_interval=10)
    assert len(result.files) == 50
    assert [u.files_found for u in updates][-1] == 50
    assert len(updates) >= 5

    seen = {"polls": 0}

    def cancel_after_a_few():
        seen["polls"] += 1
        return seen["polls"] > 5

    partial = scan_directory(tmp_path, should_cancel=cancel_after_a_few)
    assert partial.cancelled
    assert len(partial.files) < 50


def test_scan_is_deterministic_and_changes_nothing(tmp_path):
    make_tree(tmp_path, ["b.txt", "A.txt", "sub/z.png", "sub/Y.png", ".git/x", "c.pdf"])
    before = snapshot(tmp_path)
    first = scan_directory(tmp_path, recursive=True)
    second = scan_directory(tmp_path, recursive=True)
    assert [f.path for f in first.files] == [f.path for f in second.files]
    assert snapshot(tmp_path) == before