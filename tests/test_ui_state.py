from pathlib import Path

from organizer.scanner import SKIP_HIDDEN, SKIP_LINK, ScanError, ScanResult, SkippedEntry
from organizer.ui.state import (
    ScanStatus,
    issues_text,
    skip_label,
    status_badge,
    summarize_skipped,
    validation_messages,
)


def make_scan(skipped=(), errors=()):
    return ScanResult(
        source=Path("src"), recursive=False, include_hidden=False,
        skipped=list(skipped), errors=list(errors),
    )


def test_status_badges():
    assert status_badge(ScanStatus.IDLE) == ("Ready to scan", "neutral")
    assert status_badge(ScanStatus.SCANNING) == ("Scanning…", "info")
    assert status_badge(ScanStatus.SCANNING, cancelling=True) == ("Cancelling…", "warning")
    assert status_badge(ScanStatus.DONE)[1] == "success"
    assert status_badge(ScanStatus.CANCELLED)[1] == "warning"
    assert status_badge(ScanStatus.ERROR)[1] == "danger"


def test_validation_messages_without_source():
    assert validation_messages("", "")[0][0] == "muted"


def test_validation_messages_missing_source(tmp_path):
    messages = validation_messages(str(tmp_path / "nope"), "")
    assert messages[0][0] == "error"


def test_validation_messages_good_folders(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    messages = validation_messages(str(source), str(tmp_path / "src_Organized"))
    kinds = [kind for kind, _ in messages]
    assert kinds[0] == "ok"
    assert "error" not in kinds


def test_validation_messages_destination_inside_source(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    messages = validation_messages(str(source), str(source / "out"))
    assert "error" in [kind for kind, _ in messages]


def test_skip_label_and_summary_order():
    assert skip_label(SKIP_HIDDEN) == "hidden items"
    assert skip_label("something_new") == "something_new"
    skipped = [
        SkippedEntry(Path("a"), SKIP_HIDDEN),
        SkippedEntry(Path("b"), SKIP_HIDDEN),
        SkippedEntry(Path("c"), SKIP_LINK),
    ]
    assert summarize_skipped(skipped) == [("hidden items", 2), ("links and junctions", 1)]


def test_issues_text_nothing_to_report():
    assert issues_text(make_scan()) == "Nothing was skipped and no errors occurred."


def test_issues_text_lists_skipped_items_and_errors():
    scan = make_scan(
        skipped=[SkippedEntry(Path("a"), SKIP_HIDDEN), SkippedEntry(Path("b"), SKIP_HIDDEN),
                 SkippedEntry(Path("c"), SKIP_LINK)],
        errors=[ScanError(Path("locked"), "Cannot read folder: denied")],
    )
    text = issues_text(scan)
    assert "Skipped items (3)" in text
    assert "2 hidden items" in text
    assert "1 links and junctions" in text
    assert "Errors (1)" in text
    assert "denied" in text


def test_issues_text_limit():
    skipped = [SkippedEntry(Path(f"f{i}"), SKIP_HIDDEN) for i in range(5)]
    text = issues_text(make_scan(skipped=skipped), limit=2)
    assert "... and 3 more" in text