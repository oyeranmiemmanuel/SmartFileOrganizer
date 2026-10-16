import types

import pytest

from organizer.categories import default_rules
from organizer.history import HistoryStore
from organizer.jobs import build_preview, run_plan_job, undo_preflight
from organizer.planner import PlanOptions
from organizer.reports import (
    confirmation_text,
    preflight_summary,
    problem_rows,
    report_text,
    result_headline,
    run_details_text,
    undo_confirmation_text,
)
from organizer.scanner import scan_directory


@pytest.fixture
def env(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "b.jfif").write_bytes(b"BB")
    rules = default_rules()
    return types.SimpleNamespace(
        source=source,
        destination=tmp_path / "out",
        store=HistoryStore(tmp_path / "hist"),
        rules=rules,
        scan=scan_directory(source, rules=rules),
    )


def plan_and_run(env):
    options = PlanOptions()
    plan = build_preview(env.scan, {".jfif"}, env.rules, env.destination, options)
    return plan, run_plan_job(env.scan, {".jfif"}, env.rules, env.destination, options, plan, env.store)


def test_confirmation_text(env):
    plan = build_preview(env.scan, {".jfif"}, env.rules, env.destination, PlanOptions())
    text = confirmation_text(plan)
    assert "Move 1 file" in text
    assert str(plan.destination) in text
    assert "never overwritten" in text


def test_clean_run_headline_and_details(env):
    plan, outcome = plan_and_run(env)
    result = outcome.result
    assert result_headline(result) == ("Completed", "success")
    assert problem_rows(result) == []
    run = env.store.load_run(result.run_id)
    details = run_details_text(run)
    assert result.run_id in details
    assert "[done]" in details


def test_a_file_changed_after_the_preview_is_skipped_and_reported(env):
    options = PlanOptions()
    plan = build_preview(env.scan, {".jfif"}, env.rules, env.destination, options)
    (env.source / "b.jfif").write_bytes(b"changed and longer")

    outcome = run_plan_job(env.scan, {".jfif"}, env.rules, env.destination, options, plan, env.store)
    result = outcome.result

    assert result.skipped == 1 and result.succeeded == 0
    assert problem_rows(result)[0][0] == "Skipped"
    assert result_headline(result) == ("Completed: some files were skipped", "warning")
    assert "Skipped: 1" in report_text(result, plan)


def test_undo_wording(env):
    _plan, outcome = plan_and_run(env)
    summary = preflight_summary(undo_preflight(env.store, outcome.result.run_id).checks)
    assert (summary.ok, summary.blocked) == (1, 0)
    text = undo_confirmation_text(summary, "move")
    assert "move back 1 file" in text
    assert "Nothing is ever overwritten." in text