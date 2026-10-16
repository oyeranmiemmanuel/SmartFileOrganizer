import os

import pytest

from organizer import fileops
from organizer.executor import execute_plan
from organizer.history import HistoryStore
from organizer.planner import Action
from organizer.undo import check_entry, preflight, undo_run
from tests.helpers import build_plan_for, make_tree, snapshot


@pytest.fixture
def store(tmp_path):
    return HistoryStore(tmp_path / "history")


def run_and_load(store, plan):
    result = execute_plan(plan, store)
    return result, store.load_run(result.run_id)


def test_undo_move_restores_files_exactly_and_removes_created_folders(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A", "b.pdf": b"BB", "sub/c.zzz": b"C"}, recursive=True)
    for f in source.rglob("*"):
        if f.is_file():
            os.utime(f, ns=(1_600_000_000_000_000_000,) * 2)
    _, _, plan = build_plan_for(tmp_path, {}, recursive=True)
    before = snapshot(source)
    result, run = run_and_load(store, plan)
    assert result.succeeded == 3 and not (source / "a.jpg").exists()

    undo = undo_run(store, result.run_id)
    assert (undo.undone, undo.blocked, undo.failed) == (3, 0, 0)
    assert snapshot(source) == before  # same files, sizes and timestamps
    assert not dest.exists()  # folders the run created were empty and are gone
    assert store.load_run(result.run_id).undo_state == "complete"


def test_undo_copy_removes_only_the_copies(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A", "b.pdf": b"B"}, action=Action.COPY)
    result, _ = run_and_load(store, plan)
    undo = undo_run(store, result.run_id)
    assert undo.undone == 2
    assert (source / "a.jpg").read_bytes() == b"A" and (source / "b.pdf").read_bytes() == b"B"
    assert not dest.exists()


def test_undo_twice_does_nothing_the_second_time(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A"})
    result, _ = run_and_load(store, plan)
    assert undo_run(store, result.run_id).undone == 1
    again = undo_run(store, result.run_id)
    assert again.outcomes == []


def test_pre_existing_folders_and_files_are_never_removed(tmp_path, store):
    source, dest, _ = build_plan_for(tmp_path, {"a.jpg": b"A"})
    make_tree(dest, {"Images/keep.jpg": b"mine"})
    _, _, plan = build_plan_for(tmp_path, {})
    result, _ = run_and_load(store, plan)
    undo_run(store, result.run_id)
    assert (dest / "Images" / "keep.jpg").read_bytes() == b"mine"
    assert (source / "a.jpg").exists()


def test_undo_refuses_when_the_moved_file_was_modified(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"original", "b.jpg": b"other"})
    result, run = run_and_load(store, plan)
    (dest / "Images" / "a.jpg").write_bytes(b"edited by the user afterwards")
    undo = undo_run(store, result.run_id)
    assert (undo.undone, undo.blocked) == (1, 1)
    blocked = next(o for o in undo.outcomes if o.status == "blocked")
    assert "modified" in blocked.message
    assert (dest / "Images" / "a.jpg").read_bytes() == b"edited by the user afterwards"
    assert not (source / "a.jpg").exists() and (source / "b.jpg").exists()
    assert store.load_run(result.run_id).undo_state == "partial"


def test_undo_refuses_when_the_moved_file_is_gone(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"x"})
    result, _ = run_and_load(store, plan)
    (dest / "Images" / "a.jpg").unlink()
    undo = undo_run(store, result.run_id)
    assert undo.blocked == 1 and "no longer exists" in undo.outcomes[0].message


def test_undo_never_overwrites_a_new_file_at_the_original_location(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"moved"})
    result, _ = run_and_load(store, plan)
    (source / "a.jpg").write_bytes(b"a different file created since")
    undo = undo_run(store, result.run_id)
    assert undo.blocked == 1
    assert (source / "a.jpg").read_bytes() == b"a different file created since"
    assert (dest / "Images" / "a.jpg").read_bytes() == b"moved"


def test_undo_copy_is_refused_if_the_copy_changed(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A"}, action=Action.COPY)
    result, _ = run_and_load(store, plan)
    (dest / "Images" / "a.jpg").write_bytes(b"user edited the copy")
    undo = undo_run(store, result.run_id)
    assert undo.blocked == 1 and (dest / "Images" / "a.jpg").exists()


def test_undo_copy_is_refused_if_the_original_is_gone(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A"}, action=Action.COPY)
    result, _ = run_and_load(store, plan)
    (source / "a.jpg").unlink()  # the copy is now the only version
    undo = undo_run(store, result.run_id)
    assert undo.blocked == 1 and "only version" in undo.outcomes[0].message
    assert (dest / "Images" / "a.jpg").read_bytes() == b"A"


def test_undo_copy_is_refused_if_the_original_was_modified(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A"}, action=Action.COPY)
    result, _ = run_and_load(store, plan)
    (source / "a.jpg").write_bytes(b"A edited later")
    undo = undo_run(store, result.run_id)
    assert undo.blocked == 1 and (dest / "Images" / "a.jpg").exists()


def test_preflight_reports_without_changing_anything(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A", "b.jpg": b"B"})
    result, run = run_and_load(store, plan)
    (dest / "Images" / "b.jpg").write_bytes(b"changed")
    before = snapshot(tmp_path)
    checks = preflight(run)
    assert [(c.index, c.ok) for c in checks] == [(0, True), (1, False)]
    assert snapshot(tmp_path) == before


def test_undo_after_cancellation_only_touches_completed_files(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, [f"f{i}.jpg" for i in range(4)])
    seen = {"n": 0}
    result = execute_plan(plan, store, progress=lambda u: seen.update(n=u.completed),
                          should_cancel=lambda: seen["n"] >= 2)
    assert result.cancelled
    undo = undo_run(store, result.run_id)
    assert undo.undone == 2 and len(undo.outcomes) == 2
    assert sorted(p.name for p in source.iterdir()) == [f"f{i}.jpg" for i in range(4)]


def test_interrupted_run_is_undoable_but_uncertain_entry_is_left_alone(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])

    class Crash(BaseException):
        pass

    real = fileops.move_file
    calls = {"n": 0}

    def crash_on_third(src, claimed):
        calls["n"] += 1
        if calls["n"] == 3:
            raise Crash()
        return real(src, claimed)

    original = fileops.move_file
    fileops.move_file = crash_on_third
    try:
        with pytest.raises(Crash):
            execute_plan(plan, store)
    finally:
        fileops.move_file = original

    (summary,) = store.list_runs()
    assert summary.status == "interrupted"
    run = store.load_run(summary.run_id)
    assert [e.status for e in run.entries] == ["done", "done", "started"]
    undo = undo_run(store, summary.run_id)
    assert (undo.undone, undo.blocked) == (2, 1)
    assert "uncertain" in next(o for o in undo.outcomes if o.status == "blocked").message


def test_undo_cancellation_stops_between_files(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, [f"f{i}.jpg" for i in range(4)])
    result, _ = run_and_load(store, plan)
    count = {"n": 0}
    undo = undo_run(store, result.run_id, progress=lambda u: count.update(n=u.completed),
                    should_cancel=lambda: count["n"] >= 1)
    assert undo.cancelled and undo.undone == 1
    assert store.load_run(result.run_id).undo_state == "partial"
    finish = undo_run(store, result.run_id)  # resume
    assert finish.undone == 3 and store.load_run(result.run_id).undo_state == "complete"


def test_undo_survives_an_app_restart(tmp_path):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A"})
    result = execute_plan(plan, HistoryStore(tmp_path / "history"))
    fresh = HistoryStore(tmp_path / "history")  # as if the app was closed and reopened
    assert [s.run_id for s in fresh.list_runs()] == [result.run_id]
    assert undo_run(fresh, result.run_id).undone == 1
    assert (source / "a.jpg").read_bytes() == b"A"


def test_undo_move_across_drives_uses_copy_and_delete(tmp_path, store, monkeypatch):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"payload"})
    result, _ = run_and_load(store, plan)
    import errno
    monkeypatch.setattr(fileops.os, "replace", lambda *a: (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    undo = undo_run(store, result.run_id)
    assert undo.undone == 1 and (source / "a.jpg").read_bytes() == b"payload"


def test_failure_while_undoing_one_file_does_not_stop_the_rest(tmp_path, store, monkeypatch):
    source, dest, plan = build_plan_for(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])
    result, _ = run_and_load(store, plan)
    real = fileops.move_file

    def flaky(src, claimed):
        if os.path.basename(src) == "b.jpg":
            raise PermissionError("denied")
        return real(src, claimed)

    monkeypatch.setattr(fileops, "move_file", flaky)
    undo = undo_run(store, result.run_id)
    assert (undo.undone, undo.failed) == (2, 1)
    assert (dest / "Images" / "b.jpg").exists() and not (source / "b.jpg").exists()
    assert not [p for p in source.iterdir() if p.stat().st_size == 0]  # no placeholder left behind
    assert "PermissionError" in next(o for o in undo.outcomes if o.status == "failed").message


def test_check_entry_requires_verification_data(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A"})
    result, run = run_and_load(store, plan)
    from dataclasses import replace
    stripped = replace(run.entries[0], target_mtime_ns=None)
    check = check_entry(stripped)
    assert not check.ok and "verification" in check.reason


def test_created_folder_that_gained_other_files_is_kept(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A"})
    result, _ = run_and_load(store, plan)
    (dest / "Images" / "added-by-user.txt").write_bytes(b"not ours")
    undo = undo_run(store, result.run_id)
    assert undo.undone == 1 and undo.removed_dirs == []
    assert (dest / "Images" / "added-by-user.txt").read_bytes() == b"not ours"
