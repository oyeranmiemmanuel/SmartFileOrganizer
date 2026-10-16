from organizer.categories import default_rules
from organizer.plan_filters import filter_items, plan_categories, plan_extensions
from organizer.planner import PlanOptions, build_plan
from organizer.scanner import scan_directory


def make_files(root, files):
    root.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (root / name).write_bytes(content)


def make_plan(tmp_path):
    source = tmp_path / "src"
    make_files(source, {"a.txt": b"1", "b.txt": b"2", "c.jpg": b"3"})
    destination = tmp_path / "dst"
    make_files(destination / "Text Files", {"a.txt": b"old"})
    rules = default_rules()
    scan = scan_directory(source, rules=rules)
    return build_plan(scan, rules, destination, PlanOptions())


def names(items):
    return sorted(item.source.name for item in items)


def test_filters(tmp_path):
    plan = make_plan(tmp_path)
    assert names(filter_items(plan.items)) == ["a.txt", "b.txt", "c.jpg"]
    assert names(filter_items(plan.items, status="Renamed")) == ["a.txt"]
    assert names(filter_items(plan.items, status="Conflicts")) == ["a.txt"]
    assert names(filter_items(plan.items, status="Ready")) == ["b.txt", "c.jpg"]
    assert names(filter_items(plan.items, category="Images")) == ["c.jpg"]
    assert names(filter_items(plan.items, extension=".txt")) == ["a.txt", "b.txt"]
    assert names(filter_items(plan.items, text="C.JPG")) == ["c.jpg"]
    assert filter_items(plan.items, extension="") == []


def test_plan_categories_and_extensions(tmp_path):
    plan = make_plan(tmp_path)
    assert plan_categories(plan) == ["Images", "Text Files"]
    assert plan_extensions(plan) == [".jpg", ".txt"]