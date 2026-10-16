import random
from pathlib import Path

import pytest

from organizer.categories import default_rules, parse_rules
from organizer.planner import (
    Action,
    ConflictKind,
    ConflictPolicy,
    Layout,
    PlanOptions,
    PlanValidationError,
    Status,
    build_plan,
    extension_summary,
    validate_paths,
)
from organizer.scanner import scan_directory
from tests.helpers import make_tree, snapshot

RULES = default_rules()


@pytest.fixture
def dirs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    return source, tmp_path / "source_Organized"


def plan_for(source, destination, *, recursive=False, rules=RULES, **option_kwargs):
    scan = scan_directory(source, recursive=recursive, rules=rules)
    return build_plan(scan, rules, destination, PlanOptions(**option_kwargs))


def by_name(plan):
    return {item.source.name: item for item in plan.items}


# ---------------------------------------------------------------- validation


def test_valid_pair_has_no_errors(dirs):
    source, destination = dirs
    assert validate_paths(source, destination).ok


def test_missing_or_blank_paths_are_errors(tmp_path):
    assert not validate_paths("", tmp_path / "d").ok
    assert not validate_paths(tmp_path / "nope", tmp_path / "d").ok
    assert not validate_paths(tmp_path, "").ok


def test_source_that_is_a_file_is_an_error(tmp_path):
    make_tree(tmp_path, ["file.txt"])
    assert not validate_paths(tmp_path / "file.txt", tmp_path / "out").ok


def test_destination_equal_inside_or_parent_of_source_is_rejected(dirs):
    source, destination = dirs
    assert not validate_paths(source, source).ok
    assert not validate_paths(source, source / "Organized").ok
    (source / "inner").mkdir()
    assert not validate_paths(source / "inner", source).ok  # destination is a parent
    assert not validate_paths(source, source.parent).ok


def test_destination_that_is_a_file_is_rejected(dirs):
    source, destination = dirs
    destination.write_text("not a folder")
    result = validate_paths(source, destination)
    assert not result.ok and "not a folder" in result.errors[0]


def test_sibling_with_shared_prefix_is_not_treated_as_inside(tmp_path):
    (tmp_path / "data").mkdir()
    assert validate_paths(tmp_path / "data", tmp_path / "data_Organized").ok


def test_build_plan_refuses_invalid_destination(dirs):
    source, _ = dirs
    scan = scan_directory(source)
    with pytest.raises(PlanValidationError):
        build_plan(scan, RULES, source / "inside")


# ------------------------------------------------------------ targets/layout


def test_basic_plan_targets_and_categories(dirs):
    source, destination = dirs
    make_tree(source, ["photo.jpg", "doc.pdf", "notes.txt", "song.mp3", "mystery.zzz", "README", "a.tar.gz"])
    plan = plan_for(source, destination)
    found = {i.source.name: (i.category, i.target) for i in plan.items}
    assert found == {
        "photo.jpg": ("Images", destination / "Images" / "photo.jpg"),
        "doc.pdf": ("PDF", destination / "PDF" / "doc.pdf"),
        "notes.txt": ("Text Files", destination / "Text Files" / "notes.txt"),
        "song.mp3": ("Audio", destination / "Audio" / "song.mp3"),
        "mystery.zzz": ("Other Files", destination / "Other Files" / "mystery.zzz"),
        "README": ("No Extension", destination / "No Extension" / "README"),
        "a.tar.gz": ("Archives", destination / "Archives" / "a.tar.gz"),
    }
    assert all(i.status is Status.READY and i.conflict is ConflictKind.NONE for i in plan.items)
    summary = plan.summary()
    assert (summary.total, summary.ready, summary.conflicts) == (7, 7, 0)


def test_custom_folder_name_and_keyword_rule_shape_the_target(dirs):
    source, destination = dirs
    make_tree(source, ["photo.jpg", "invoice march.pdf"])
    rules, _ = parse_rules(
        {"folder_names": {"Images": "Pictures"}, "keyword_rules": [{"keyword": "invoice", "folder": "Invoices"}]}
    )
    items = by_name(plan_for(source, destination, rules=rules))
    assert items["photo.jpg"].target == destination / "Pictures" / "photo.jpg"
    assert items["invoice march.pdf"].target == destination / "Invoices" / "invoice march.pdf"
    assert items["invoice march.pdf"].classification_reason == "keyword"


def test_flatten_layout_ignores_source_folders(dirs):
    source, destination = dirs
    make_tree(source, ["top.jpg", "a/b/deep.jpg"])
    plan = plan_for(source, destination, recursive=True, layout=Layout.FLATTEN)
    assert {i.target for i in plan.items} == {
        destination / "Images" / "top.jpg",
        destination / "Images" / "deep.jpg",
    }


def test_preserve_layout_keeps_relative_folders_under_category(dirs):
    source, destination = dirs
    make_tree(source, ["top.jpg", "a/b/deep.jpg", "a/doc.pdf"])
    plan = plan_for(source, destination, recursive=True, layout=Layout.PRESERVE_STRUCTURE)
    assert {i.target for i in plan.items} == {
        destination / "Images" / "top.jpg",
        destination / "Images" / "a" / "b" / "deep.jpg",
        destination / "PDF" / "a" / "doc.pdf",
    }


def test_action_is_recorded_on_every_item(dirs):
    source, destination = dirs
    make_tree(source, ["a.jpg", "b.png"])
    plan = plan_for(source, destination, action=Action.COPY)
    assert {i.action for i in plan.items} == {Action.COPY}


# ----------------------------------------------------------------- conflicts


def test_existing_destination_file_is_renamed_never_overwritten(dirs):
    source, destination = dirs
    make_tree(source, ["photo.jpg"])
    make_tree(destination, {"Images/photo.jpg": b"existing", "Images/photo (1).jpg": b"existing"})
    plan = plan_for(source, destination)
    (item,) = plan.items
    assert item.status is Status.RENAMED
    assert item.conflict is ConflictKind.EXISTS_ON_DISK
    assert item.target == destination / "Images" / "photo (2).jpg"
    assert item.desired_target == destination / "Images" / "photo.jpg"
    assert (destination / "Images" / "photo.jpg").read_bytes() == b"existing"


def test_existing_destination_file_with_skip_policy(dirs):
    source, destination = dirs
    make_tree(source, ["photo.jpg", "other.jpg"])
    make_tree(destination, {"Images/photo.jpg": b"existing"})
    plan = plan_for(source, destination, conflict_policy=ConflictPolicy.SKIP)
    items = by_name(plan)
    assert items["photo.jpg"].status is Status.SKIPPED
    assert items["photo.jpg"].target is None
    assert items["photo.jpg"].conflict is ConflictKind.EXISTS_ON_DISK
    assert items["other.jpg"].status is Status.READY
    assert [i.source.name for i in plan.executable_items] == ["other.jpg"]
    assert plan.summary().skipped == 1 and plan.summary().conflicts == 1


def test_conflict_matching_ignores_case(dirs):
    source, destination = dirs
    make_tree(source, ["Photo.JPG"])
    make_tree(destination, {"Images/photo.jpg": b"existing"})
    (item,) = plan_for(source, destination).items
    assert item.conflict is ConflictKind.EXISTS_ON_DISK
    assert item.target.name == "Photo (1).JPG"


def test_duplicates_within_the_plan_are_resolved_deterministically(dirs):
    source, destination = dirs
    make_tree(source, ["one/report.pdf", "two/report.pdf", "three/Report.PDF"])
    plan = plan_for(source, destination, recursive=True)
    # Sorted by source path: one/report.pdf, three/Report.PDF, two/report.pdf
    assert [(i.source.parent.name, i.target.name) for i in plan.items] == [
        ("one", "report.pdf"),
        ("three", "Report (1).PDF"),
        ("two", "report (2).pdf"),
    ]
    assert len({str(i.target).casefold() for i in plan.items}) == 3  # all distinct, case-insensitively
    kinds = sorted(i.conflict.value for i in plan.items)
    assert kinds == ["duplicate_in_plan", "duplicate_in_plan", "none"]
    assert all(i.status in (Status.READY, Status.RENAMED) for i in plan.items)


def test_duplicates_within_the_plan_with_skip_policy(dirs):
    source, destination = dirs
    make_tree(source, ["one/report.pdf", "two/report.pdf"])
    plan = plan_for(source, destination, recursive=True, conflict_policy=ConflictPolicy.SKIP)
    statuses = sorted(i.status.value for i in plan.items)
    assert statuses == ["ready", "skipped"]
    skipped = next(i for i in plan.items if i.status is Status.SKIPPED)
    assert skipped.conflict is ConflictKind.DUPLICATE_IN_PLAN


def test_preserving_structure_avoids_duplicate_conflicts(dirs):
    source, destination = dirs
    make_tree(source, ["one/report.pdf", "two/report.pdf"])
    plan = plan_for(source, destination, recursive=True, layout=Layout.PRESERVE_STRUCTURE)
    assert all(i.conflict is ConflictKind.NONE for i in plan.items)


def test_rename_keeps_compound_extension_intact(dirs):
    source, destination = dirs
    make_tree(source, ["backup.tar.gz"])
    make_tree(destination, {"Archives/backup.tar.gz": b"existing"})
    (item,) = plan_for(source, destination).items
    assert item.target.name == "backup (1).tar.gz"


def test_rename_extensionless_file(dirs):
    source, destination = dirs
    make_tree(source, ["README"])
    make_tree(destination, {"No Extension/README": b"existing"})
    (item,) = plan_for(source, destination).items
    assert item.target.name == "README (1)"


def test_directory_in_the_way_counts_as_a_conflict(dirs):
    source, destination = dirs
    make_tree(source, ["photo.jpg"])
    (destination / "Images" / "photo.jpg").mkdir(parents=True)
    (item,) = plan_for(source, destination).items
    assert item.status is Status.RENAMED and item.target.name == "photo (1).jpg"


# ------------------------------------------------------------ blocked items


def test_category_folder_occupied_by_a_file_blocks_the_item(dirs):
    source, destination = dirs
    make_tree(source, ["photo.jpg", "doc.pdf"])
    make_tree(destination, {"Images": b"i am a file, not a folder"})
    items = by_name(plan_for(source, destination))
    assert items["photo.jpg"].status is Status.BLOCKED
    assert "not a folder" in items["photo.jpg"].message
    assert items["photo.jpg"].target is None
    assert items["doc.pdf"].status is Status.READY


def test_overlong_target_paths_are_blocked(dirs):
    source, destination = dirs
    make_tree(source, ["short.jpg", "a_rather_long_file_name_indeed.jpg"])
    limit = len(str(destination / "Images" / "short.jpg"))
    items = by_name(plan_for(source, destination, max_path_length=limit))
    assert items["short.jpg"].status is Status.READY
    assert items["a_rather_long_file_name_indeed.jpg"].status is Status.BLOCKED
    assert "limit" in items["a_rather_long_file_name_indeed.jpg"].message


def test_rename_that_would_exceed_the_limit_is_blocked(dirs):
    source, destination = dirs
    make_tree(source, ["photo.jpg"])
    make_tree(destination, {"Images/photo.jpg": b"existing"})
    limit = len(str(destination / "Images" / "photo.jpg"))  # fits as-is, not with " (1)"
    (item,) = plan_for(source, destination, max_path_length=limit).items
    assert item.status is Status.BLOCKED and item.conflict is ConflictKind.EXISTS_ON_DISK


# ------------------------------------------------- stability and read-only


def test_plan_is_stable_regardless_of_scan_order(dirs):
    source, destination = dirs
    make_tree(source, [f"d{n % 3}/file{n % 7}.txt" for n in range(30)] + ["x/a.jpg", "y/A.JPG"])
    scan = scan_directory(source, recursive=True)
    reference = build_plan(scan, RULES, destination)
    for seed in range(5):
        random.Random(seed).shuffle(scan.files)
        again = build_plan(scan, RULES, destination)
        assert again.items == reference.items
        assert again.fingerprint() == reference.fingerprint()


def test_fingerprint_changes_when_the_plan_changes(dirs):
    source, destination = dirs
    make_tree(source, ["a.jpg"])
    base = plan_for(source, destination)
    assert plan_for(source, destination, action=Action.COPY).fingerprint() != base.fingerprint()
    (source / "a.jpg").write_bytes(b"changed contents")
    assert plan_for(source, destination).fingerprint() != base.fingerprint()


def test_items_have_sequential_indexes_in_sorted_order(dirs):
    source, destination = dirs
    make_tree(source, ["b.txt", "A.txt", "c.txt"])
    plan = plan_for(source, destination)
    assert [i.index for i in plan.items] == [0, 1, 2]
    assert [i.source.name for i in plan.items] == ["A.txt", "b.txt", "c.txt"]


def test_scanning_and_planning_never_touch_the_disk(dirs):
    source, destination = dirs
    make_tree(source, ["a.jpg", "sub/b.jpg", "sub/c.pdf", ".git/x"])
    make_tree(destination, {"Images/a.jpg": b"existing"})
    before_source, before_destination = snapshot(source), snapshot(destination)
    existed_before = destination.exists()
    plan = plan_for(source, destination, recursive=True)
    assert len(plan.items) == 3
    assert snapshot(source) == before_source
    assert snapshot(destination) == before_destination
    assert destination.exists() == existed_before


def test_planning_does_not_create_a_missing_destination(dirs):
    source, destination = dirs
    make_tree(source, ["a.jpg"])
    plan = plan_for(source, destination)
    assert plan.items[0].status is Status.READY
    assert not destination.exists()


def test_empty_source_gives_empty_plan(dirs):
    source, destination = dirs
    plan = plan_for(source, destination)
    assert plan.items == () and plan.summary().total == 0


# ------------------------------------------------------------------- summary


def test_extension_summary_rows(dirs):
    source, destination = dirs
    make_tree(source, {"a.jpg": b"12", "b.JPG": b"123", "c.pdf": b"1", "README": b"", "d.zzz": b"1234"})
    rows = extension_summary(scan_directory(source), RULES)
    first = rows[0]
    assert (first.extension, first.count, first.total_size, first.category, first.folder) == (
        ".jpg", 2, 5, "Images", "Images",
    )
    table = {r.label: (r.count, r.category, r.folder) for r in rows}
    assert table == {
        ".jpg": (2, "Images", "Images"),
        ".pdf": (1, "PDF", "PDF"),
        "(no extension)": (1, "No Extension", "No Extension"),
        ".zzz": (1, "Other Files", "Other Files"),
    }