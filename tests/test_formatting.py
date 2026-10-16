import pytest

from organizer.formatting import format_bytes, format_count, plural, shorten_path


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (-5, "0 B"),
        (0, "0 B"),
        (1, "1 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024**2, "1.0 MB"),
        (5 * 1024**3, "5.0 GB"),
        (1024**4, "1.0 TB"),
    ],
)
def test_format_bytes(size, expected):
    assert format_bytes(size) == expected


def test_format_count():
    assert format_count(0) == "0"
    assert format_count(1234567) == "1,234,567"


def test_plural():
    assert plural(1, "file") == "1 file"
    assert plural(2, "file") == "2 files"
    assert plural(1234, "file") == "1,234 files"
    assert plural(0, "entry", "entries") == "0 entries"
    assert plural(1, "entry", "entries") == "1 entry"


def test_shorten_path_keeps_short_paths():
    assert shorten_path("C:\\short", 60) == "C:\\short"


def test_shorten_path_shortens_in_the_middle():
    path = "C:\\Users\\Someone\\Documents\\Projects\\Very\\Deep\\Folder\\Structure\\file.txt"
    shortened = shorten_path(path, 40)
    assert len(shortened) == 40
    assert "…" in shortened
    assert shortened.startswith(path[:5])
    assert shortened.endswith(path[-5:])