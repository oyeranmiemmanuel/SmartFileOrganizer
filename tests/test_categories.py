import json
from collections import Counter

import pytest

from organizer.categories import (
    DEFAULT_CATEGORIES,
    KEYWORD_CATEGORY,
    NO_EXTENSION_CATEGORY,
    UNKNOWN_CATEGORY,
    RulesError,
    default_rules,
    get_extension,
    load_rules,
    parse_rules,
    rules_template,
)

RULES = default_rules()


def test_each_extension_belongs_to_exactly_one_category():
    counts = Counter(ext for exts in DEFAULT_CATEGORIES.values() for ext in exts)
    assert [ext for ext, n in counts.items() if n > 1] == []
    assert all(ext == ext.lower() and ext.startswith(".") for ext in counts)


@pytest.mark.parametrize(
    "filename, category",
    [
        # Images
        ("a.jpg", "Images"), ("a.jpeg", "Images"), ("a.png", "Images"), ("a.gif", "Images"),
        ("a.bmp", "Images"), ("a.webp", "Images"), ("a.jfif", "Images"), ("a.tif", "Images"),
        ("a.tiff", "Images"), ("a.heic", "Images"), ("a.ico", "Images"),
        # Documents and text
        ("a.pdf", "PDF"), ("a.doc", "Documents"), ("a.docx", "Documents"),
        ("a.odt", "Documents"), ("a.rtf", "Documents"), ("a.txt", "Text Files"),
        ("a.md", "Text Files"),
        # Data
        ("a.csv", "Data"), ("a.json", "Data"), ("a.xml", "Data"), ("a.sql", "Data"),
        ("a.xlsx", "Spreadsheets"), ("a.pptx", "Presentations"),
        # Media
        ("a.mp3", "Audio"), ("a.flac", "Audio"), ("a.mp4", "Videos"), ("a.mkv", "Videos"),
        # Archives
        ("a.zip", "Archives"), ("a.7z", "Archives"), ("a.tar", "Archives"),
        ("a.tar.gz", "Archives"), ("a.tgz", "Archives"), ("a.tar.xz", "Archives"),
        # Programs and code
        ("a.exe", "Executables"), ("a.msi", "Executables"), ("a.bat", "Scripts"),
        ("a.ps1", "Scripts"), ("a.py", "Development"), ("a.js", "Development"),
        ("a.html", "Development"),
        # Legacy categories from the original app
        ("a.cdr", "CorelDRAW"), ("a.svg", "Vector Files"), ("a.psd", "Design Files"),
    ],
)
def test_default_classification(filename, category):
    result = RULES.classify(filename)
    assert result.category == category
    assert result.folder == category
    assert result.reason == "extension"


def test_extensions_are_case_insensitive():
    assert RULES.classify("PHOTO.JPG").category == "Images"
    assert RULES.classify("Backup.TAR.GZ").category == "Archives"
    assert RULES.classify("Backup.TAR.GZ").extension == ".tar.gz"


def test_compound_extension_wins_over_last_suffix():
    assert get_extension("archive.tar.gz", RULES.compound_extensions) == ".tar.gz"
    assert get_extension("archive.gz", RULES.compound_extensions) == ".gz"
    assert RULES.compound_extensions == tuple(sorted(RULES.compound_extensions, key=len, reverse=True))


def test_extensionless_and_dotfiles():
    for name in ["README", "Makefile", ".gitignore", "trailing.", "Mr. Smith notes"]:
        result = RULES.classify(name)
        assert result.extension == "", name
        assert result.category == NO_EXTENSION_CATEGORY, name
        assert result.reason == "no_extension"


def test_unknown_extension_is_preserved_as_unknown_not_guessed():
    result = RULES.classify("mystery.zzzzz")
    assert (result.category, result.folder, result.extension, result.reason) == (
        UNKNOWN_CATEGORY, "Other Files", ".zzzzz", "unknown",
    )


def test_keyword_rule_beats_extension_and_is_case_insensitive():
    rules, warnings = parse_rules(
        {"keyword_rules": [{"keyword": "Burna Boy", "folder": "Burna Boy Songs"}]}
    )
    assert warnings == []
    hit = rules.classify("01 - burna BOY - Ye.mp3")
    assert (hit.category, hit.folder, hit.reason, hit.extension) == (
        KEYWORD_CATEGORY, "Burna Boy Songs", "keyword", ".mp3",
    )
    assert rules.classify("other song.mp3").category == "Audio"


def test_first_matching_keyword_rule_wins():
    rules, _ = parse_rules(
        {"keyword_rules": [{"keyword": "tax", "folder": "Taxes"}, {"keyword": "2024", "folder": "Y2024"}]}
    )
    assert rules.classify("tax 2024.pdf").folder == "Taxes"
    assert rules.classify("budget 2024.pdf").folder == "Y2024"


def test_overlay_renames_folder_and_overrides_extension():
    rules, warnings = parse_rules(
        {
            "folder_names": {"images": "Pictures"},  # category match ignores case
            "extension_overrides": {"XYZ": "Images", ".abc": "My Stuff", ".pdf": "Documents"},
        }
    )
    assert warnings == []
    assert rules.classify("a.jpg").folder == "Pictures"
    assert rules.classify("a.xyz").category == "Images"
    assert rules.classify("a.xyz").folder == "Pictures"
    assert (rules.classify("a.abc").category, rules.classify("a.abc").folder) == ("My Stuff", "My Stuff")
    assert rules.classify("a.pdf").category == "Documents"
    # The shared defaults must not be modified by an overlay.
    assert default_rules().classify("a.pdf").category == "PDF"


def test_overlay_can_merge_two_categories_into_one_folder():
    rules, _ = parse_rules({"folder_names": {"PDF": "Documents", "Text Files": "Documents"}})
    assert {rules.classify(n).folder for n in ["a.pdf", "a.doc", "a.txt"]} == {"Documents"}
    assert rules.classify("a.pdf").category == "PDF"  # categories stay distinct


def test_overlay_can_unclassify_an_extension():
    rules, _ = parse_rules({"extension_overrides": {".txt": UNKNOWN_CATEGORY}})
    assert rules.classify("a.txt").category == UNKNOWN_CATEGORY


def test_overlay_unknown_and_no_extension_folders():
    rules, warnings = parse_rules({"unknown_folder": "Misc", "no_extension_folder": "Plain"})
    assert warnings == []
    assert rules.classify("a.zzzzz").folder == "Misc"
    assert rules.classify("README").folder == "Plain"


def test_overlay_sanitizes_folder_names_and_warns():
    rules, warnings = parse_rules({"folder_names": {"Images": "bad/name:"}})
    assert rules.classify("a.png").folder == "bad_name_"
    assert any("changed" in w for w in warnings)


def test_bad_overlay_entries_become_warnings_not_crashes():
    rules, warnings = parse_rules(
        {
            "extension_overrides": {"not valid!": "Images", ".ok": "", ".fine": "Images", "5": 3},
            "keyword_rules": [{"folder": "no keyword"}, "nonsense", {"keyword": "  "}],
            "folder_names": {"Images": ""},
            "surprise": 1,
            "_comment": "ignored silently",
        }
    )
    assert rules.classify("a.fine").category == "Images"
    assert rules.keyword_rules == ()
    assert len(warnings) >= 6
    assert not any("_comment" in w for w in warnings)


@pytest.mark.parametrize("bad", [[], "text", 5, None])
def test_non_object_rules_file_is_an_error(bad):
    with pytest.raises(RulesError):
        parse_rules(bad)


def test_newer_rules_version_is_rejected():
    with pytest.raises(RulesError):
        parse_rules({"version": 99})


def test_load_rules_missing_file_gives_defaults(tmp_path):
    rules, warnings = load_rules(tmp_path / "nope.json")
    assert warnings == [] and rules.classify("a.png").category == "Images"
    assert load_rules(None).rules.classify("a.png").category == "Images"


def test_load_rules_reads_utf8_with_bom(tmp_path):
    path = tmp_path / "rules.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"folder_names": {"Images": "Pics"}}).encode())
    assert load_rules(path).rules.classify("a.png").folder == "Pics"


def test_load_rules_malformed_json_raises_with_location(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text('{"folder_names": {', encoding="utf-8")
    with pytest.raises(RulesError, match="line 1"):
        load_rules(path)


def test_template_is_loadable_and_changes_nothing(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(rules_template()), encoding="utf-8")
    rules, warnings = load_rules(path)
    assert warnings == []
    for name in ["a.jpg", "a.pdf", "a.zzzzz", "README", "a.tar.gz"]:
        assert rules.classify(name) == RULES.classify(name)