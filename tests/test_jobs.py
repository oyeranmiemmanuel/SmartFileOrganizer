import types

import pytest

from organizer.categories import default_rules
from organizer.history import HistoryStore
from organizer.jobs import build_preview, run_plan_job, undo_preflight
from organizer.planner import Action, PlanOptions
from organizer.scanner import scan_directory
from organizer.undo import undo_run

FILES = {"a.txt": b"A", "b.jfif": b"BB", "c.pdf": b"CCC"}


def make_files(root, files):
    root.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (root / name).write_bytes(content)


@pytest.fixture
def env(tmp_path):
    source = tmp_path / "src"
    make_files(source, FILES)
    rules = default_rules()
    return types.SimpleNamespace(
        source=source,
        destination=tmp_path / "out",
        store=HistoryStore(tmp_path / "hist"),
        rules=rules,
        scan=scan_directory(source, rules=rules),
    )


def run(env, selected, options=None, plan=None):
    options = options or PlanOptions()
    plan = plan or build_preview(env.scan, selected, env.rules, env.destination, options)
    return plan, run_plan_job(env.scan, selected, env.rules, env.destination, options, plan, env.store)


def test_preview_covers_only_the_selected_types_and_changes_nothing(env):
    plan = build_preview(env.scan, {".jfif"}, env.rules, env.destination, PlanOptions())
    assert [item.source.name for item in plan.items] == ["b.jfif"]
    assert plan.items[0].category == "Images"
    assert not env.destination.exists()


def test_run_moves_only_the_selected_type(env):
    _plan, outcome = run(env, {".jfif"})
    assert outcome.changed_plan is None
    assert outcome.result.succeeded == 1
    assert not (env.source / "b.jfif").exists()
    assert (env.destination / "Images" / "b.jfif").read_bytes() == b"BB"
    assert (env.source / "a.txt").exists() and (env.source / "c.pdf").exists()


def test_run_can_copy(env):
    _plan, outcome = run(env, {".jfif"}, PlanOptions(action=Action.COPY))
    assert outcome.result.succeeded == 1
    assert (env.source / "b.jfif").exists()
    assert (env.destination / "Images" / "b.jfif").exists()


def test_a_changed_destination_returns_a_fresh_plan_and_runs_nothing(env):
    options = PlanOptions()
    plan = build_preview(env.scan, {".jfif"}, env.rules, env.destination, options)
    make_files(env.destination / "Images", {"b.jfif": b"someone else's file"})

    outcome = run_plan_job(env.scan, {".jfif"}, env.rules, env.destination, options, plan, env.store)

    assert outcome.result is None
    assert outcome.changed_plan is not None
    assert outcome.changed_plan.items[0].target.name == "b (1).jfif"
    assert (env.source / "b.jfif").exists()
    assert env.store.list_runs() == []


def test_undo_check_and_undo_restore_the_file(env):
    _plan, outcome = run(env, {".jfif"})
    run_id = outcome.result.run_id

    pre = undo_preflight(env.store, run_id)
    assert [check.ok for check in pre.checks] == [True]

    undone = undo_run(env.store, run_id)
    assert undone.undone == 1
    assert (env.source / "b.jfif").read_bytes() == b"BB"
    assert not (env.destination / "Images" / "b.jfif").exists()