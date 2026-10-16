import errno
import os

import pytest

from organizer import executor, fileops
from organizer.executor import OutcomeStatus, execute_plan
from organizer.history import RUN_CANCELLED, RUN_COMPLETED, HistoryStore
from organizer.planner import Action, ConflictPolicy, Layout, PlanValidationError
from tests.helpers import build_plan_for, make_tree, snapshot


@pytest.fixture
def store(tmp_path):
    return HistoryStore(tmp_path / "history")


def by_name(result):
    return {o.source.name: o for o in result.outcomes}


def test_move_moves_files_into_category_folders(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A", "b.pdf": b"BB", "c.zzz": b"CCC"})
    result = execute_plan(plan, store)
    assert (result.succeeded, result.skipped, result.failed, result.cancelled) == (3, 0, 0, False)
    assert not any(source.iterdir())
    assert (dest / "Images" / "a.jpg").read_bytes() == b"A"
    assert (dest / "PDF" / "b.pdf").read_bytes() == b"BB"
    assert (dest / "Other Files" / "c.zzz").read_bytes() == b"CCC"
    assert result.bytes_done == 6


def test_copy_leaves_sources_in_place_and_keeps_timestamps(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"A"}, action=Action.COPY)
    os.utime(source / "a.jpg", ns=(1_600_000_000_000_000_000,) * 2)
    _, _, plan = build_plan_for(tmp_path, {}, action=Action.COPY)
    result = execute_plan(plan, store)
    assert result.succeeded == 1
    assert (source / "a.jpg").read_bytes() == b"A"
    assert (dest / "Images" / "a.jpg").stat().st_mtime_ns == 1_600_000_000_000_000_000


def test_preserve_structure_creates_nested_folders(tmp_path, store):
    source, dest, plan = build_plan_for(
        tmp_path, ["x/y/p.jpg"], recursive=True, layout=Layout.PRESERVE_STRUCTURE
    )
    execute_plan(plan, store)
    assert (dest / "Images" / "x" / "y" / "p.jpg").exists()


def test_existing_destination_files_are_never_overwritten(tmp_path, store):
    source, dest, _ = build_plan_for(tmp_path, {"a.jpg": b"NEW"})
    make_tree(dest, {"Images/a.jpg": b"OLD"})
    _, _, plan = build_plan_for(tmp_path, {})  # re-plan now that the conflict exists
    result = execute_plan(plan, store)
    assert (dest / "Images" / "a.jpg").read_bytes() == b"OLD"
    assert (dest / "Images" / "a (1).jpg").read_bytes() == b"NEW"
    assert result.succeeded == 1


def test_file_that_appears_after_the_preview_is_not_overwritten_and_is_renamed(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"NEW"})
    make_tree(dest, {"Images/a.jpg": b"LATE ARRIVAL"})  # created after the plan was built
    result = execute_plan(plan, store)
    outcome = result.outcomes[0]
    assert outcome.status is OutcomeStatus.DONE and outcome.target.name == "a (1).jpg"
    assert "taken after the preview" in outcome.message
    assert (dest / "Images" / "a.jpg").read_bytes() == b"LATE ARRIVAL"


def test_late_conflict_with_skip_policy_skips(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"NEW"}, conflict_policy=ConflictPolicy.SKIP)
    make_tree(dest, {"Images/a.jpg": b"LATE ARRIVAL"})
    result = execute_plan(plan, store)
    assert result.outcomes[0].status is OutcomeStatus.SKIPPED
    assert (source / "a.jpg").read_bytes() == b"NEW"
    assert sorted(p.name for p in (dest / "Images").iterdir()) == ["a.jpg"]


def test_plan_level_skips_and_duplicates_are_reported(tmp_path, store):
    source, dest, plan = build_plan_for(
        tmp_path, {"one/r.pdf": b"1", "two/r.pdf": b"2"}, recursive=True, conflict_policy=ConflictPolicy.SKIP
    )
    result = execute_plan(plan, store)
    assert (result.succeeded, result.skipped) == (1, 1)
    skipped = next(o for o in result.outcomes if o.status is OutcomeStatus.SKIPPED)
    assert skipped.message.startswith("Skipped.") and skipped.target is None
    assert skipped.source.exists()


def test_blocked_plan_items_are_not_executed(tmp_path, store):
    source, dest, _ = build_plan_for(tmp_path, {"a.jpg": b"x", "b.pdf": b"y"})
    dest.mkdir()
    (dest / "Images").write_bytes(b"i am a file")
    _, _, plan = build_plan_for(tmp_path, {})
    result = execute_plan(plan, store)
    assert (result.succeeded, result.skipped) == (1, 1)
    blocked = by_name(result)["a.jpg"]
    assert blocked.message.startswith("Blocked.") and (source / "a.jpg").exists()


def test_source_deleted_after_preview_is_skipped(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, ["a.jpg", "b.jpg"])
    (source / "a.jpg").unlink()
    result = execute_plan(plan, store)
    assert by_name(result)["a.jpg"].status is OutcomeStatus.SKIPPED
    assert "no longer exists" in by_name(result)["a.jpg"].message
    assert by_name(result)["b.jpg"].status is OutcomeStatus.DONE


def test_source_modified_after_preview_is_skipped_not_moved(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"before"})
    (source / "a.jpg").write_bytes(b"edited after the preview")
    result = execute_plan(plan, store)
    assert result.outcomes[0].status is OutcomeStatus.SKIPPED
    assert "changed after the preview" in result.outcomes[0].message
    assert (source / "a.jpg").read_bytes() == b"edited after the preview"
    assert not dest.exists()


def test_source_replaced_by_a_symlink_is_skipped(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"x"})
    (tmp_path / "elsewhere.jpg").write_bytes(b"x")
    (source / "a.jpg").unlink()
    try:
        (source / "a.jpg").symlink_to(tmp_path / "elsewhere.jpg")
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available in this environment")
    result = execute_plan(plan, store)
    assert result.outcomes[0].status is OutcomeStatus.SKIPPED
    assert (tmp_path / "elsewhere.jpg").exists()


def test_destination_folder_that_became_a_link_is_refused(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"x"})
    outside = tmp_path / "outside"
    outside.mkdir()
    dest.mkdir()
    try:
        (dest / "Images").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available in this environment")
    result = execute_plan(plan, store)
    assert result.outcomes[0].status is OutcomeStatus.FAILED
    assert "link" in result.outcomes[0].message
    assert list(outside.iterdir()) == [] and (source / "a.jpg").exists()


def test_one_failure_does_not_stop_the_others_and_leaves_no_debris(tmp_path, store, monkeypatch):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"a", "b.jpg": b"b", "c.jpg": b"c"})
    real_move = fileops.move_file

    def flaky(src, claimed):
        if os.path.basename(src) == "b.jpg":
            raise PermissionError(errno.EACCES, "Access is denied")
        return real_move(src, claimed)

    monkeypatch.setattr(fileops, "move_file", flaky)
    result = execute_plan(plan, store)
    outcomes = by_name(result)
    assert outcomes["b.jpg"].status is OutcomeStatus.FAILED
    assert "PermissionError" in outcomes["b.jpg"].message
    assert outcomes["a.jpg"].status is outcomes["c.jpg"].status is OutcomeStatus.DONE
    assert (source / "b.jpg").read_bytes() == b"b"  # source untouched
    assert sorted(p.name for p in (dest / "Images").iterdir()) == ["a.jpg", "c.jpg"]  # no empty placeholder
    assert (result.succeeded, result.failed) == (2, 1)
    assert store.load_run(result.run_id).status == RUN_COMPLETED


def test_failed_copy_removes_partial_target(tmp_path, store, monkeypatch):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"a"}, action=Action.COPY)

    def disk_full(src, claimed):
        with open(claimed, "wb") as partial:
            partial.write(b"par")
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(fileops, "copy_file", disk_full)
    result = execute_plan(plan, store)
    assert result.outcomes[0].status is OutcomeStatus.FAILED
    assert list((dest / "Images").iterdir()) == [] and (source / "a.jpg").exists()


def test_cross_drive_move_through_the_executor(tmp_path, store, monkeypatch):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"payload"})
    monkeypatch.setattr(fileops.os, "replace", lambda *a: (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    result = execute_plan(plan, store)
    assert result.succeeded == 1
    assert not (source / "a.jpg").exists() and (dest / "Images" / "a.jpg").read_bytes() == b"payload"


def test_cancellation_stops_between_files_and_marks_the_rest(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, [f"f{i}.jpg" for i in range(6)])
    seen = {"done": 0}

    def progress(update):
        seen["done"] = update.completed

    result = execute_plan(plan, store, progress=progress, should_cancel=lambda: seen["done"] >= 2)
    assert result.cancelled
    assert (result.succeeded, result.not_run) == (2, 4)
    assert all(o.status is OutcomeStatus.CANCELLED and o.target is None for o in result.outcomes[2:])
    assert sorted(p.name for p in source.iterdir()) == ["f2.jpg", "f3.jpg", "f4.jpg", "f5.jpg"]
    run = store.load_run(result.run_id)
    assert run.status == RUN_CANCELLED and run.count("cancelled") == 4 and run.count("done") == 2


def test_cancel_before_start_changes_nothing(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, ["a.jpg", "b.jpg"])
    before = snapshot(source)
    result = execute_plan(plan, store, should_cancel=lambda: True)
    assert result.cancelled and result.not_run == 2 and snapshot(source) == before
    assert not dest.exists()


def test_progress_is_accurate_and_monotonic(tmp_path, store):
    source, dest, plan = build_plan_for(
        tmp_path, {"a.jpg": b"1" * 10, "b.jpg": b"2" * 20, "c.pdf": b"3" * 30, "d.jpg": b"4"},
    )
    (source / "d.jpg").unlink()  # one operation will be skipped
    updates = []
    result = execute_plan(plan, store, progress=updates.append)
    assert updates[0].completed == 0 and updates[-1].current is None
    assert [u.completed for u in updates] == sorted(u.completed for u in updates)
    final = updates[-1]
    assert (final.total, final.completed, final.succeeded, final.skipped, final.failed) == (4, 4, 3, 1, 0)
    assert final.bytes_total == 61 and final.bytes_done == 60
    assert any(u.current and u.current.name == "a.jpg" for u in updates)
    assert result.callback_errors == 0


def test_a_broken_progress_callback_does_not_abort_the_run(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, ["a.jpg", "b.jpg"])

    def broken(update):
        raise RuntimeError("UI exploded")

    result = execute_plan(plan, store, progress=broken)
    assert result.succeeded == 2 and result.callback_errors > 0


def test_invalid_destination_is_rejected_before_anything_happens(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, ["a.jpg"])
    bad = type(plan)(plan.source, plan.source / "inside", plan.options, plan.items)
    with pytest.raises(PlanValidationError):
        execute_plan(bad, store)
    assert (source / "a.jpg").exists() and store.list_runs() == []


def test_source_folder_removed_after_preview_is_rejected(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, ["a.jpg"])
    (source / "a.jpg").unlink()
    source.rmdir()
    with pytest.raises(PlanValidationError):
        execute_plan(plan, store)


def test_empty_plan_still_records_a_run_and_creates_nothing(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, [])
    result = execute_plan(plan, store)
    assert result.outcomes == [] and not dest.exists()
    assert store.load_run(result.run_id).status == RUN_COMPLETED


def test_history_records_actual_targets_and_created_folders(tmp_path, store):
    source, dest, _ = build_plan_for(tmp_path, {"a.jpg": b"NEW"})
    make_tree(dest, {"Images/a.jpg": b"OLD"})
    _, _, plan = build_plan_for(tmp_path, {})
    result = execute_plan(plan, store)
    run = store.load_run(result.run_id)
    entry = run.entries[0]
    assert entry.target == str(dest / "Images" / "a (1).jpg")
    assert (entry.target_size, entry.size, entry.status) == (3, 3, "done")
    assert run.created_dirs == ()  # Images already existed

    source2, dest2, plan2 = build_plan_for(tmp_path / "second", {"p.pdf": b"x"})
    run2 = store.load_run(execute_plan(plan2, store).run_id)
    assert run2.created_dirs == (str(dest2), str(dest2 / "PDF"))
    assert run2.fingerprint == plan2.fingerprint()


def test_executor_only_touches_planned_files(tmp_path, store):
    source, dest, plan = build_plan_for(tmp_path, {"a.jpg": b"x"})
    bystander = tmp_path / "bystander.txt"
    bystander.write_bytes(b"leave me")
    (source / "late.png").write_bytes(b"added after the preview")
    execute_plan(plan, store)
    assert bystander.read_bytes() == b"leave me"
    assert (source / "late.png").exists()
