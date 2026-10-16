import csv
import json

import pytest

from organizer.history import (
    ENTRY_DONE,
    ENTRY_STARTED,
    RUN_COMPLETED,
    RUN_INTERRUPTED,
    UNDO_DONE,
    EntryRecord,
    HistoryError,
    HistoryStore,
    export_run_csv,
)


def new_run(store, total=2):
    return store.start_run(
        source="S", destination="D", action="move", conflict_policy="rename",
        layout="flatten", fingerprint="abc", total_items=total,
    )


def done_entry(index, **kw):
    base = dict(index=index, action="move", source=f"S/{index}.txt", target=f"D/{index}.txt",
                status=ENTRY_DONE, size=3, source_mtime_ns=1, target_size=3, target_mtime_ns=1)
    base.update(kw)
    return EntryRecord(**base)


def test_run_round_trips_through_disk(tmp_path):
    store = HistoryStore(tmp_path / "hist")
    with new_run(store) as writer:
        run_id = writer.run_id
        writer.created_dirs(["D/Images"])
        writer.intent(done_entry(0))
        writer.entry(done_entry(0))
        writer.entry(done_entry(1, status="failed", message="boom", target=None))
        writer.finish(RUN_COMPLETED, {"done": 1, "failed": 1})
    run = HistoryStore(tmp_path / "hist").load_run(run_id)  # a fresh store: as after a restart
    assert (run.status, run.source, run.destination, run.fingerprint) == (RUN_COMPLETED, "S", "D", "abc")
    assert [e.status for e in run.entries] == ["done", "failed"]
    assert run.created_dirs == ("D/Images",)
    assert run.count("failed") == 1 and run.finished_at


def test_intent_without_entry_reads_as_started_and_run_as_interrupted(tmp_path):
    store = HistoryStore(tmp_path)
    writer = new_run(store)
    writer.intent(done_entry(0))
    writer.close()  # simulates a crash: no end line
    run = store.load_run(writer.run_id)
    assert run.status == RUN_INTERRUPTED
    assert run.entries[0].status == ENTRY_STARTED
    assert not run.entries[0].undo_status


def test_damaged_and_unknown_lines_are_ignored(tmp_path):
    store = HistoryStore(tmp_path)
    with new_run(store) as writer:
        writer.entry(done_entry(0))
        writer.entry(done_entry(1))
        writer.finish(RUN_COMPLETED, {"done": 2})
    path = tmp_path / f"{writer.run_id}.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.insert(2, "this is not json")
    lines.insert(3, json.dumps({"type": "future-feature", "x": 1}))
    lines.append('{"type": "entry", "index": 9, "act')  # half-written last line
    path.write_text("\n".join(lines), encoding="utf-8")
    run = store.load_run(writer.run_id)
    assert [e.index for e in run.entries] == [0, 1]
    assert run.skipped_lines == 2  # the garbage line and the truncated line


def test_undo_events_are_applied_and_counted(tmp_path):
    store = HistoryStore(tmp_path)
    with new_run(store) as writer:
        writer.entry(done_entry(0))
        writer.entry(done_entry(1))
        writer.finish(RUN_COMPLETED, {"done": 2})
    assert store.load_run(writer.run_id).undo_state == "none"
    store.record_undo(writer.run_id, 1, UNDO_DONE, "ok")
    run = store.load_run(writer.run_id)
    assert run.undo_state == "partial"
    assert [e.index for e in run.undoable_entries] == [0]
    assert run.entries[1].undo_message == "ok" and run.entries[1].undo_at
    store.record_undo(writer.run_id, 0, UNDO_DONE)
    assert store.load_run(writer.run_id).undo_state == "complete"


def test_list_runs_newest_first_with_counts(tmp_path):
    store = HistoryStore(tmp_path)
    ids = []
    for n in range(3):
        with new_run(store) as writer:
            writer.entry(done_entry(0))
            writer.entry(done_entry(1, status="skipped"))
            writer.finish(RUN_COMPLETED, {"done": 1, "skipped": 1})
            ids.append(writer.run_id)
    store.record_undo(ids[0], 0, UNDO_DONE)
    summaries = store.list_runs()
    assert len(summaries) == 3
    assert [s.run_id for s in summaries] == sorted(ids, reverse=True)
    first = next(s for s in summaries if s.run_id == ids[0])
    assert (first.done, first.skipped, first.failed, first.undone, first.status) == (1, 1, 0, 1, RUN_COMPLETED)


def test_list_runs_includes_interrupted_run_and_skips_junk(tmp_path):
    store = HistoryStore(tmp_path)
    writer = new_run(store)
    writer.entry(done_entry(0))
    writer.close()
    (tmp_path / "garbage.jsonl").write_text("not json\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    summaries = store.list_runs()
    assert [(s.run_id, s.status, s.done) for s in summaries] == [(writer.run_id, RUN_INTERRUPTED, 1)]


def test_list_runs_on_missing_directory_is_empty(tmp_path):
    assert HistoryStore(tmp_path / "nope").list_runs() == []


@pytest.mark.parametrize("bad", ["../escape", "a/b", "..", "", "x" * 200, "with space"])
def test_run_ids_cannot_escape_the_history_folder(tmp_path, bad):
    with pytest.raises(HistoryError):
        HistoryStore(tmp_path).load_run(bad)


def test_unknown_run_raises(tmp_path):
    with pytest.raises(HistoryError):
        HistoryStore(tmp_path).load_run("20200101-000000-aaaaaa")


def test_unicode_paths_survive(tmp_path):
    store = HistoryStore(tmp_path)
    with new_run(store) as writer:
        writer.entry(done_entry(0, source="S/Café – 音楽 \U0001F3B5.mp3"))
        writer.finish(RUN_COMPLETED, {"done": 1})
    assert store.load_run(writer.run_id).entries[0].source == "S/Café – 音楽 \U0001F3B5.mp3"


def test_csv_export(tmp_path):
    store = HistoryStore(tmp_path)
    with new_run(store) as writer:
        writer.entry(done_entry(0, source='S/odd, "name".txt'))
        writer.finish(RUN_COMPLETED, {"done": 1})
    out = tmp_path / "out.csv"
    export_run_csv(store.load_run(writer.run_id), out)
    rows = list(csv.reader(out.read_text(encoding="utf-8-sig").splitlines()))
    assert rows[0][:4] == ["timestamp", "action", "source", "target"]
    assert rows[1][1:4] == ["move", 'S/odd, "name".txt', "D/0.txt"]
