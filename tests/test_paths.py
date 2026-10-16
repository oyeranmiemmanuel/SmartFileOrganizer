import pytest

from organizer.paths import (
    default_destination,
    is_within,
    same_path,
    sanitize_name,
    sanitize_relative_parts,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Images", "Images"),
        ("My Photos 2024", "My Photos 2024"),
        ("  padded  ", "padded"),
        ("a/b", "a_b"),
        ("a\\b", "a_b"),
        ('bad<>:"|?*chars', "bad_______chars"),
        ("tab\there", "tab_here"),
        ("trailing dots...", "trailing dots"),
        ("trailing space. ", "trailing space"),
        ("..", "_"),
        (".", "_"),
        ("", "_"),
        ("   ", "_"),
        ("...", "_"),
        ("CON", "_CON"),
        ("con", "_con"),
        ("NUL.txt", "_NUL.txt"),
        ("COM1", "_COM1"),
        ("LPT9", "_LPT9"),
        ("CONSOLE", "CONSOLE"),
        (".hidden", ".hidden"),
        ("Café Ünïcode", "Café Ünïcode"),
    ],
)
def test_sanitize_name(raw, expected):
    assert sanitize_name(raw) == expected


def test_sanitize_name_never_contains_separators_or_traversal():
    for raw in ["../../etc", "..\\..\\Windows", "/abs/path", "C:\\Windows", "a/../b"]:
        cleaned = sanitize_name(raw)
        assert "/" not in cleaned and "\\" not in cleaned and ":" not in cleaned
        assert cleaned not in ("", ".", "..")


def test_sanitize_name_truncates_and_strips_after_truncation():
    cleaned = sanitize_name("x" * 150)
    assert len(cleaned) == 100
    # Truncation must not leave a trailing dot or space behind.
    assert sanitize_name("a" * 99 + ". b", max_length=100) == "a" * 99


def test_sanitize_relative_parts_keeps_valid_names_unchanged():
    assert sanitize_relative_parts(["Holiday 2024", "day 1"]) == ("Holiday 2024", "day 1")
    assert sanitize_relative_parts(["a:b", "CON"]) == ("a_b", "_CON")


def test_same_path_and_is_within(tmp_path):
    parent = tmp_path / "parent"
    child = parent / "child"
    assert same_path(parent, parent / ".")
    assert is_within(child, parent)
    assert not is_within(parent, parent)
    assert not is_within(parent, child)
    # A sibling whose name merely starts with the same text is not inside.
    assert not is_within(tmp_path / "parent2", parent)


def test_default_destination_is_sibling_named_organized(tmp_path):
    source = tmp_path / "Downloads"
    assert default_destination(source) == tmp_path / "Downloads_Organized"
    assert not is_within(default_destination(source), source)