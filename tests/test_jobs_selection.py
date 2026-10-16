from organizer.categories import default_rules
from organizer.history import HistoryStore
from organizer.jobs import build_preview, run_plan_job
from organizer.planner import PlanOptions
from organizer.scanner import scan_directory
from organizer.selection import Selection, file_key


def test_preview_and_run_only_the_chosen_files(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    for name in ("a.txt", "b.txt", "c.txt"):
        (source / name).write_bytes(name.encode())
    destination = tmp_path / "out"
    store = HistoryStore(tmp_path / "hist")
    rules = default_rules()
    scan = scan_directory(source, rules=rules)
    chosen = next(file_key(item) for item in scan.files if item.name == "b.txt")
    selection = Selection(files=frozenset({chosen}))
    options = PlanOptions()

    plan = build_preview(scan, selection, rules, destination, options)
    assert [item.source.name for item in plan.items] == ["b.txt"]

    outcome = run_plan_job(scan, selection, rules, destination, options, plan, store)

    assert outcome.changed_plan is None
    assert outcome.result.succeeded == 1
    assert (destination / "Text Files" / "b.txt").read_bytes() == b"b.txt"
    assert (source / "a.txt").exists() and (source / "c.txt").exists()
    assert not (source / "b.txt").exists()