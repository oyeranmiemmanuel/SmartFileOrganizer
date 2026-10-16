import json

import pytest

from organizer.categories import NO_EXTENSION_CATEGORY, UNKNOWN_CATEGORY, RulesError, parse_rules
from organizer.rules_editor import (
    add_keyword_rule,
    backup_file,
    clear_category_folder,
    clear_extension_override,
    load_overlay,
    new_overlay,
    remove_keyword_rule,
    save_overlay,
    set_category_folder,
    set_extension_category,
)


def test_missing_file_gives_an_empty_overlay(tmp_path):
    overlay = load_overlay(tmp_path / "none.json")
    assert overlay["version"] == 1
    assert overlay["extension_overrides"] == {}


def test_broken_files_raise(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    with pytest.raises(RulesError):
        load_overlay(bad)
    listing = tmp_path / "list.json"
    listing.write_text("[1]", encoding="utf-8")
    with pytest.raises(RulesError):
        load_overlay(listing)


def test_extension_override_changes_classification():
    overlay = new_overlay()
    set_extension_category(overlay, "XYZ", "Photos")
    rules = parse_rules(overlay).rules
    result = rules.classify("a.xyz")
    assert (result.category, result.folder) == ("Photos", "Photos")


def test_setting_the_default_category_removes_the_override():
    overlay = new_overlay()
    set_extension_category(overlay, ".jpg", "Photos")
    assert overlay["extension_overrides"][".jpg"] == "Photos"
    set_extension_category(overlay, ".jpg", "Images")
    assert ".jpg" not in overlay["extension_overrides"]


def test_spelling_variants_of_an_extension_are_replaced():
    overlay = new_overlay()
    overlay["extension_overrides"] = {"JPG": "X"}
    set_extension_category(overlay, ".jpg", "Y")
    assert overlay["extension_overrides"] == {".jpg": "Y"}
    clear_extension_override(overlay, "jpg")
    assert overlay["extension_overrides"] == {}


def test_empty_values_are_rejected():
    overlay = new_overlay()
    with pytest.raises(ValueError):
        set_extension_category(overlay, "", "Photos")
    with pytest.raises(ValueError):
        set_extension_category(overlay, ".abc", "  ")
    with pytest.raises(ValueError):
        set_category_folder(overlay, "Images", " ")
    with pytest.raises(ValueError):
        add_keyword_rule(overlay, "", "Folder")


def test_category_folder_names():
    overlay = new_overlay()
    set_category_folder(overlay, "Images", "Pictures")
    set_category_folder(overlay, UNKNOWN_CATEGORY, "Unsorted")
    set_category_folder(overlay, NO_EXTENSION_CATEGORY, "Plain")
    rules = parse_rules(overlay).rules
    assert rules.folder_for("Images") == "Pictures"
    assert rules.unknown_folder == "Unsorted"
    assert rules.no_extension_folder == "Plain"

    clear_category_folder(overlay, "Images")
    clear_category_folder(overlay, UNKNOWN_CATEGORY)
    clear_category_folder(overlay, NO_EXTENSION_CATEGORY)
    rules = parse_rules(overlay).rules
    assert rules.folder_for("Images") == "Images"
    assert rules.unknown_folder == UNKNOWN_CATEGORY
    assert rules.no_extension_folder == NO_EXTENSION_CATEGORY


def test_keyword_rules_add_replace_remove():
    overlay = new_overlay()
    add_keyword_rule(overlay, "Invoice", "Invoices")
    add_keyword_rule(overlay, "invoice", "Bills")
    assert overlay["keyword_rules"] == [{"keyword": "invoice", "folder": "Bills"}]
    rules = parse_rules(overlay).rules
    assert rules.classify("My INVOICE 3.pdf").folder == "Bills"
    remove_keyword_rule(overlay, "INVOICE")
    assert overlay["keyword_rules"] == []


def test_save_and_load_round_trip_with_backup(tmp_path):
    path = tmp_path / "sub" / "rules.json"
    overlay = new_overlay()
    set_extension_category(overlay, ".xyz", "Photos")
    save_overlay(path, overlay)
    assert load_overlay(path) == overlay
    assert not list(path.parent.glob("*.tmp"))
    assert json.loads(path.read_text(encoding="utf-8"))["extension_overrides"] == {".xyz": "Photos"}

    backup = backup_file(path)
    assert backup is not None and backup.read_text(encoding="utf-8") == path.read_text(encoding="utf-8")
    assert backup_file(tmp_path / "missing.json") is None