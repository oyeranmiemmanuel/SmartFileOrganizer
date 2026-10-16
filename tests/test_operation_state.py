from organizer.categories import default_rules
from organizer.history import RunSummary
from organizer.planner import Action, ConflictPolicy, Layout, PlanOptions, build_plan
from organizer.scanner import scan_directory
from organizer.ui.operation_state import (
    PlanStatus,
    RunStatus,
    history_row,
    plan_badge,
    plan_options,
    preview_row,
    run_badge,
)


def test_plan_options_from_labels():
    options = plan_options("Copy", "Skip conflicting files", "Keep subfolder structure")
    assert options.action is Action.COPY
    assert options.conflict_policy is ConflictPolicy.SKIP
    assert options.layout is Layout.PRESERVE_STRUCTURE


def test_unknown_labels_use_safe_defaults():
    options = plan_options("???", "???", "???")
    assert options.action is Action.MOVE
    assert options.conflict_policy is ConflictPolicy.RENAME
    assert options.layout is Layout.FLATTEN


def test_badges():
    assert plan_badge(PlanStatus.READY)[1] == "success"
    assert plan_badge(PlanStatus.ERROR)[1] == "danger"
    assert run_badge(RunStatus.IDLE) == ("No operation yet", "neutral")
    assert run_badge(RunStatus.RUNNING) == ("Running…", "info")
    assert run_badge(RunStatus.RUNNING, cancelling=True) == ("Cancelling…", "warning")
    assert run_badge(RunStatus.ERROR)[1] == "danger"


def test_preview_row(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.txt").write_bytes(b"12345")
    rules = default_rules()
    plan = build_plan(scan_directory(source, rules=rules), rules, tmp_path / "dst", PlanOptions())
    row = preview_row(plan.items[0], plan)
    assert row[0] == "Ready"
    assert row[1] == "a.txt"
    assert row[2] == str(__import__("pathlib").Path("Text Files") / "a.txt")
    assert row[3] == "Text Files"
    assert row[4] == 5
    assert row[-1] == 0


def test_history_row():
    summary = RunSummary(
        run_id="20261014-123005-abc123", started_at="2026-10-14T12:30:05+01:00", finished_at=None,
        source="C:\\src", destination="C:\\dst", action="move", status="completed",
        total_items=3, done=2, skipped=1, failed=0, undone=0,
    )
    row = history_row(summary)
    assert row[0] == "2026-10-14 12:30:05"
    assert row[1] == "Move"
    assert row[4:8] == (2, 1, 0, 0)
    assert row[8] == "Completed"
    assert row[-1] == "20261014-123005-abc123"