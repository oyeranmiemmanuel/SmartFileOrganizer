import os
from datetime import datetime

import pytest

from organizer.categories import default_rules
from organizer.paths import path_key
from organizer.scanner import scan_directory
from organizer.search import (
    SearchError,
    build_criteria,
    find_files,
    format_mtime,
    parse_day,
    parse_extensions,
    parse_size,
)

OLD = datetime(2020, 1, 15, 12, 0).timestamp()


def make_tree(tmp_path):
    source = tmp_path / "src"
    (source / "sub").mkdir(parents=True, exist_ok=True)
    files = {
        "Invoice March.pdf": 2048,
        "invoice_april.PDF": 100,
        "holiday.jfif": 5000,
        "notes.txt": 10,
        "README": 1,
        "sub/invoice old.txt": 300,
    }
    for name, size in files.items():
        (source / name).write_bytes(b"x" * size)
    os.utime(source / "notes.txt", (OLD, OLD))
    return source


def search(tmp_path, recursive=False, **criteria):
    rules = default_rules()
    scan = scan_directory(make_tree(tmp_path), recursive=recursive, rules=rules)
    return {hit.file.name for hit in find_files(scan, build_criteria(**criteria), rules)}


def test_contains_ignores_case(tmp_path):
    assert search(tmp_path, text="INVOICE") == {"Invoice March.pdf", "invoice_april.PDF"}


def test_recursive_scan_includes_subfolder_files(tmp_path):
    found = search(tmp_path, recursive=True, text="invoice")
    assert found == {"Invoice March.pdf", "invoice_april.PDF", "invoice old.txt"}


def test_starts_with_and_ends_with(tmp_path):
    assert search(tmp_path, match="starts", text="inv") == {"Invoice March.pdf", "invoice_april.PDF"}
    assert search(tmp_path, match="ends", text=".pdf") == {"Invoice March.pdf", "invoice_april.PDF"}


def test_wildcards(tmp_path):
    both = {"Invoice March.pdf", "invoice_april.PDF"}
    assert search(tmp_path, match="wildcard", text="*.PDF") == both
    assert search(tmp_path, match="wildcard", text="invoice_*") == {"invoice_april.PDF"}
    assert search(tmp_path, match="wildcard", text="inv?ice*") == both
    assert search(tmp_path, match="wildcard", text="hol") == {"holiday.jfif"}  # no * or ?: "contains"


def test_extensions(tmp_path):
    found = search(tmp_path, extensions_text="jfif, .PDF")
    assert found == {"Invoice March.pdf", "invoice_april.PDF", "holiday.jfif"}
    assert search(tmp_path, extensions_text="none") == {"README"}


def test_size_limits(tmp_path):
    assert search(tmp_path, min_size_text="1", size_unit="KB") == {"Invoice March.pdf", "holiday.jfif"}
    assert search(tmp_path, max_size_text="0.5", size_unit="KB") == {"invoice_april.PDF", "notes.txt", "README"}


def test_modified_dates(tmp_path):
    assert search(tmp_path, modified_to_text="2020-01-31") == {"notes.txt"}
    assert search(tmp_path, modified_from_text="2020-01-01", modified_to_text="2020-01-15") == {"notes.txt"}
    assert "notes.txt" not in search(tmp_path, modified_from_text="2021-01-01")


def test_category(tmp_path):
    assert search(tmp_path, category="PDF") == {"Invoice March.pdf", "invoice_april.PDF"}
    assert search(tmp_path, category="Images") == {"holiday.jfif"}


def test_subfolder_text(tmp_path):
    assert search(tmp_path, recursive=True, folder_text="SUB") == {"invoice old.txt"}


def test_criteria_are_combined_with_and(tmp_path):
    found = search(tmp_path, text="invoice", extensions_text="pdf", min_size_text="1", size_unit="KB")
    assert found == {"Invoice March.pdf"}


def test_empty_criteria_match_everything(tmp_path):
    assert build_criteria().is_empty
    assert len(search(tmp_path)) == 5


def test_hits_carry_key_and_category(tmp_path):
    rules = default_rules()
    scan = scan_directory(make_tree(tmp_path), rules=rules)
    hits = find_files(scan, build_criteria(text="holiday"), rules)
    assert len(hits) == 1
    assert hits[0].key == path_key(hits[0].file.path)
    assert hits[0].category == "Images"


def test_parsers():
    assert parse_extensions("jpg, .PNG tar.gz none") == frozenset({".jpg", ".png", ".tar.gz", ""})
    assert parse_extensions("   ") is None
    assert parse_size("1.5", "MB") == int(1.5 * 1024**2)
    assert parse_size("2", "KB") == 2048
    assert parse_size("", "MB") is None
    assert parse_day("2020/01/15") == datetime(2020, 1, 15).date()
    assert parse_day("") is None


@pytest.mark.parametrize(
    "call",
    [
        lambda: parse_extensions("bad/ext"),
        lambda: parse_size("abc"),
        lambda: parse_size("-1"),
        lambda: parse_size("1", "TB"),
        lambda: parse_day("2020-13-45"),
        lambda: build_criteria(min_size_text="5", max_size_text="1"),
        lambda: build_criteria(modified_from_text="2020-02-01", modified_to_text="2020-01-01"),
        lambda: build_criteria(match="regex"),
    ],
)
def test_invalid_input_is_reported(call):
    with pytest.raises(SearchError):
        call()


def test_format_mtime():
    assert format_mtime(int(OLD * 1_000_000_000)) == "2020-01-15 12:00"