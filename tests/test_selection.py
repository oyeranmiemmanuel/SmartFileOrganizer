from organizer.categories import default_rules
from organizer.scanner import scan_directory
from organizer.selection import (
    Selection,
    all_extensions,
    as_selection,
    file_key,
    filter_scan,
    summarize_selection,
)


def make_scan(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.jfif").write_bytes(b"12")
    (source / "b.txt").write_bytes(b"123")
    (source / "README").write_bytes(b"1234")
    return scan_directory(source, rules=default_rules())


def names(scan):
    return sorted(item.name for item in scan.files)


def test_all_extensions_includes_the_empty_one(tmp_path):
    assert all_extensions(make_scan(tmp_path)) == {".jfif", ".txt", ""}


def test_filter_scan_keeps_only_chosen_types_and_leaves_the_original(tmp_path):
    scan = make_scan(tmp_path)
    filtered = filter_scan(scan, {".jfif"})
    assert names(filtered) == ["a.jfif"]
    assert len(scan.files) == 3


def test_filter_scan_can_select_files_without_an_extension(tmp_path):
    assert names(filter_scan(make_scan(tmp_path), {""})) == ["README"]


def test_empty_selection_selects_nothing(tmp_path):
    scan = make_scan(tmp_path)
    assert filter_scan(scan, set()).files == []
    assert filter_scan(scan, Selection(files=frozenset())).files == []


def test_summarize_selection_by_types(tmp_path):
    scan = make_scan(tmp_path)
    summary = summarize_selection(scan, {".jfif", ".txt"})
    assert (summary.files, summary.size) == (2, 5)
    assert (summary.extensions, summary.total_extensions) == (2, 3)
    assert summarize_selection(scan, set()).files == 0


def test_selection_by_individual_files(tmp_path):
    scan = make_scan(tmp_path)
    keys = frozenset(file_key(item) for item in scan.files if item.name in ("a.jfif", "README"))
    selection = Selection(files=keys)
    assert selection.by_files
    assert names(filter_scan(scan, selection)) == ["README", "a.jfif"]
    summary = summarize_selection(scan, selection)
    assert (summary.files, summary.size) == (2, 6)
    assert (summary.extensions, summary.total_extensions) == (2, 3)


def test_files_selection_ignores_the_extensions_field(tmp_path):
    scan = make_scan(tmp_path)
    key = next(file_key(item) for item in scan.files if item.name == "b.txt")
    selection = Selection(extensions=frozenset({".jfif"}), files=frozenset({key}))
    assert names(filter_scan(scan, selection)) == ["b.txt"]


def test_as_selection():
    selection = Selection(extensions=frozenset({".a"}))
    assert as_selection(selection) is selection
    assert as_selection({".a", ".b"}).extensions == frozenset({".a", ".b"})
    assert not as_selection({".a"}).by_files