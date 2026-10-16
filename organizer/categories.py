"""File classification rules.

Extensions are treated as *hints* about a file's type, never as proof of its
contents. A file with an unrecognized or missing extension is classified as
such and left for the user to decide about; its contents are never inspected.

Users change classifications by editing a JSON "rules file" (see
``load_rules``), not Python source. The file is an overlay on top of the
built-in defaults, so it only needs to list what the user wants to change:

    {
      "version": 1,
      "folder_names": {"Images": "Pictures"},
      "extension_overrides": {".xyz": "Images", ".abc": "My Custom Category"},
      "keyword_rules": [{"keyword": "invoice", "folder": "Invoices"}],
      "unknown_folder": "Other Files",
      "no_extension_folder": "No Extension"
    }
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Mapping, NamedTuple

from .paths import sanitize_name

RULES_VERSION = 1
NO_EXTENSION_LABEL = "(no extension)"

# Category names double as the default destination folder names.
UNKNOWN_CATEGORY = "Other Files"
NO_EXTENSION_CATEGORY = "No Extension"
KEYWORD_CATEGORY = "Keyword Matches"


def _exts(text: str) -> tuple[str, ...]:
    return tuple("." + word for word in text.split())


# category -> extensions. Each extension appears under exactly one category
# (enforced by a test). ".ts" is treated as TypeScript, although it can also be
# an MPEG transport stream: extensions are hints only.
DEFAULT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Images": _exts(
        "jpg jpeg jpe jfif png gif bmp webp tif tiff heic heif avif ico apng jp2 "
        "cr2 cr3 nef arw dng orf rw2 raf"
    ),
    "Vector Files": _exts("svg ai eps emf wmf"),
    "Design Files": _exts("psd psb xcf indd idml sketch fig xd afdesign afphoto kra"),
    "CorelDRAW": _exts("cdr cdt cmx"),
    "PDF": _exts("pdf"),
    "Documents": _exts("doc docx dot dotx docm odt ott rtf wpd wps pages tex"),
    "Text Files": _exts("txt md markdown rst log text nfo"),
    "Spreadsheets": _exts("xls xlsx xlsm xlsb xlt xltx ods numbers"),
    "Presentations": _exts("ppt pptx pps ppsx pptm potx odp key"),
    "Data": _exts(
        "csv tsv json jsonl ndjson xml sql db sqlite sqlite3 mdb accdb parquet avro"
    ),
    "Audio": _exts("mp3 wav m4a flac aac ogg oga opus wma aiff aif mid midi amr ape"),
    "Videos": _exts(
        "mp4 mov avi mkv wmv flv webm m4v mpg mpeg mpe 3gp 3g2 mts m2ts vob ogv"
    ),
    "Archives": _exts("zip rar 7z tar gz tgz bz2 tbz2 xz txz zst lz lzma cab z")
    + (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst", ".tar.lz", ".tar.z"),
    "Disk Images": _exts("iso img dmg vhd vhdx vmdk"),
    "Executables": _exts("exe msi msix msixbundle appx appxbundle apk dll"),
    "Scripts": _exts("bat cmd ps1 psm1 vbs vbe wsf sh bash zsh fish reg ahk"),
    "Development": _exts(
        "py pyw pyi ipynb js mjs cjs jsx ts tsx java class jar c h cpp cc cxx hpp cs "
        "go rs rb php swift kt kts lua pl r dart scala html htm css scss sass less "
        "vue svelte sln csproj"
    ),
    "Config Files": _exts("ini cfg conf toml yaml yml properties"),
    "Fonts": _exts("ttf otf woff woff2 ttc eot fon"),
    "Ebooks": _exts("epub mobi azw azw3 fb2 djvu cbz cbr"),
    "CAD & 3D": _exts("dwg dxf stl obj fbx blend step stp 3mf skp iges igs gltf glb"),
    "Shortcuts": _exts("lnk url"),
}

_EXT_PATTERN = re.compile(r"^\.[a-z0-9][a-z0-9_+~\-]{0,15}$")
_OVERRIDE_EXT_PATTERN = re.compile(r"^\.[a-z0-9][a-z0-9_+~.\-]{0,31}$")


class RulesError(ValueError):
    """The rules file could not be read or is structurally invalid."""


class Classification(NamedTuple):
    category: str
    folder: str
    extension: str  # lowercase, with leading dot; "" when the file has none
    reason: str  # "keyword" | "extension" | "unknown" | "no_extension"


@dataclass(frozen=True)
class KeywordRule:
    keyword: str
    folder: str


def get_extension(filename: str, compound_extensions: tuple[str, ...] = ()) -> str:
    """Return the lowercase extension of ``filename`` ("" if it has none).

    ``compound_extensions`` (such as ``.tar.gz``) must be sorted longest first;
    the first one that matches wins. Dotfiles (``.gitignore``) and names whose
    "extension" is clearly not one (``Mr. Smith notes``) count as extensionless.
    """
    lower = filename.lower()
    for compound in compound_extensions:
        if lower.endswith(compound) and len(lower) > len(compound):
            return compound
    suffix = os.path.splitext(lower)[1]
    return suffix if _EXT_PATTERN.match(suffix) else ""


@dataclass(frozen=True)
class ClassificationRules:
    extension_map: Mapping[str, str]  # extension -> category
    folder_map: Mapping[str, str]  # category -> destination folder name
    keyword_rules: tuple[KeywordRule, ...] = ()
    unknown_folder: str = UNKNOWN_CATEGORY
    no_extension_folder: str = NO_EXTENSION_CATEGORY

    @cached_property
    def compound_extensions(self) -> tuple[str, ...]:
        found = [ext for ext in self.extension_map if ext.count(".") > 1]
        return tuple(sorted(found, key=len, reverse=True))

    @property
    def categories(self) -> list[str]:
        names = set(self.extension_map.values()) | set(self.folder_map)
        names |= {UNKNOWN_CATEGORY, NO_EXTENSION_CATEGORY}
        return sorted(names, key=str.casefold)

    def extension_of(self, filename: str) -> str:
        return get_extension(filename, self.compound_extensions)

    def folder_for(self, category: str) -> str:
        if category == UNKNOWN_CATEGORY:
            return self.unknown_folder
        if category == NO_EXTENSION_CATEGORY:
            return self.no_extension_folder
        return self.folder_map.get(category) or sanitize_name(category)

    def classify_extension(self, extension: str) -> Classification:
        """Classify by extension only (keyword rules are not considered)."""
        if not extension:
            return Classification(
                NO_EXTENSION_CATEGORY, self.no_extension_folder, "", "no_extension"
            )
        category = self.extension_map.get(extension)
        if category is None:
            return Classification(UNKNOWN_CATEGORY, self.unknown_folder, extension, "unknown")
        return Classification(category, self.folder_for(category), extension, "extension")

    def classify(self, filename: str) -> Classification:
        """Classify a file name. Keyword rules win over extension rules."""
        extension = self.extension_of(filename)
        folded = filename.casefold()
        for rule in self.keyword_rules:
            if rule.keyword.casefold() in folded:
                return Classification(KEYWORD_CATEGORY, rule.folder, extension, "keyword")
        return self.classify_extension(extension)


class LoadedRules(NamedTuple):
    rules: ClassificationRules
    warnings: list[str]


def default_rules() -> ClassificationRules:
    extension_map = {ext: cat for cat, exts in DEFAULT_CATEGORIES.items() for ext in exts}
    folder_map = {category: category for category in DEFAULT_CATEGORIES}
    return ClassificationRules(extension_map=extension_map, folder_map=folder_map)


def rules_template() -> dict[str, Any]:
    """An empty overlay a user can copy and edit."""
    return {
        "_help": (
            "Edit this file to change how files are classified. "
            "folder_names renames a category's destination folder; "
            "extension_overrides maps an extension to a category (new names create "
            "new categories); keyword_rules sends files whose NAME contains a keyword "
            "to a folder before extension rules apply."
        ),
        "version": RULES_VERSION,
        "folder_names": {},
        "extension_overrides": {},
        "keyword_rules": [],
        "unknown_folder": UNKNOWN_CATEGORY,
        "no_extension_folder": NO_EXTENSION_CATEGORY,
    }


def parse_rules(data: Any) -> LoadedRules:
    """Apply a rules overlay (already-parsed JSON) to the defaults.

    Raises ``RulesError`` for structural problems. Bad individual entries are
    skipped and reported in the returned warnings instead.
    """
    if not isinstance(data, dict):
        raise RulesError("The rules file must contain a JSON object.")
    version = data.get("version", RULES_VERSION)
    if not isinstance(version, int) or isinstance(version, bool):
        raise RulesError("'version' must be a whole number.")
    if version > RULES_VERSION:
        raise RulesError(
            f"Rules file version {version} is newer than this program supports ({RULES_VERSION})."
        )

    warnings: list[str] = []
    known = {"version", "folder_names", "extension_overrides", "keyword_rules",
             "unknown_folder", "no_extension_folder"}
    for key in data:
        if key not in known and not str(key).startswith("_"):
            warnings.append(f"Unknown setting '{key}' was ignored.")

    base = default_rules()
    extension_map = dict(base.extension_map)
    folder_map = dict(base.folder_map)
    canonical = {name.casefold(): name for name in set(extension_map.values())}
    canonical[UNKNOWN_CATEGORY.casefold()] = UNKNOWN_CATEGORY
    canonical[NO_EXTENSION_CATEGORY.casefold()] = NO_EXTENSION_CATEGORY

    def resolve_category(name: str) -> str:
        name = name.strip()
        return canonical.setdefault(name.casefold(), name)

    def clean_folder(value: Any, where: str) -> str | None:
        if not isinstance(value, str) or not value.strip():
            warnings.append(f"{where}: folder name must be non-empty text; ignored.")
            return None
        cleaned = sanitize_name(value)
        if cleaned != value.strip():
            warnings.append(f"{where}: folder name '{value}' was changed to '{cleaned}'.")
        return cleaned

    overrides = data.get("extension_overrides", {})
    if not isinstance(overrides, dict):
        warnings.append("'extension_overrides' must be an object; ignored.")
        overrides = {}
    for raw_ext, raw_cat in overrides.items():
        ext = str(raw_ext).strip().lower()
        if ext and not ext.startswith("."):
            ext = "." + ext
        if not _OVERRIDE_EXT_PATTERN.match(ext):
            warnings.append(f"Extension '{raw_ext}' is not valid; ignored.")
            continue
        if not isinstance(raw_cat, str) or not raw_cat.strip():
            warnings.append(f"Extension '{raw_ext}': category must be non-empty text; ignored.")
            continue
        category = resolve_category(raw_cat)
        if category == UNKNOWN_CATEGORY:
            extension_map.pop(ext, None)  # explicitly unclassified
        else:
            extension_map[ext] = category
            folder_map.setdefault(category, sanitize_name(category))

    folder_names = data.get("folder_names", {})
    if not isinstance(folder_names, dict):
        warnings.append("'folder_names' must be an object; ignored.")
        folder_names = {}
    for raw_cat, raw_folder in folder_names.items():
        folder = clean_folder(raw_folder, f"Category '{raw_cat}'")
        if folder is not None:
            folder_map[resolve_category(str(raw_cat))] = folder

    keyword_rules: list[KeywordRule] = []
    raw_rules = data.get("keyword_rules", [])
    if not isinstance(raw_rules, list):
        warnings.append("'keyword_rules' must be a list; ignored.")
        raw_rules = []
    for position, entry in enumerate(raw_rules, start=1):
        where = f"Keyword rule #{position}"
        if not isinstance(entry, dict) or not isinstance(entry.get("keyword"), str) \
                or not entry["keyword"].strip():
            warnings.append(f"{where}: needs a non-empty 'keyword'; ignored.")
            continue
        folder = clean_folder(entry.get("folder", KEYWORD_CATEGORY), where)
        if folder is not None:
            keyword_rules.append(KeywordRule(entry["keyword"].strip(), folder))

    unknown_folder = UNKNOWN_CATEGORY
    if "unknown_folder" in data:
        unknown_folder = clean_folder(data["unknown_folder"], "'unknown_folder'") or UNKNOWN_CATEGORY
    no_ext_folder = NO_EXTENSION_CATEGORY
    if "no_extension_folder" in data:
        no_ext_folder = (
            clean_folder(data["no_extension_folder"], "'no_extension_folder'")
            or NO_EXTENSION_CATEGORY
        )

    rules = ClassificationRules(
        extension_map=extension_map,
        folder_map=folder_map,
        keyword_rules=tuple(keyword_rules),
        unknown_folder=unknown_folder,
        no_extension_folder=no_ext_folder,
    )
    return LoadedRules(rules, warnings)


def load_rules(path: str | os.PathLike[str] | None = None) -> LoadedRules:
    """Load the user's rules file, or the defaults if there is none.

    A missing file is normal and yields the defaults. An unreadable or
    malformed file raises ``RulesError`` rather than silently falling back, so
    the user finds out their customizations are not being applied.
    """
    if path is None or not Path(path).exists():
        return LoadedRules(default_rules(), [])
    try:
        # utf-8-sig tolerates the BOM that Windows Notepad adds.
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise RulesError(f"Could not read rules file '{path}': {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RulesError(
            f"Rules file '{path}' is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}"
        ) from exc
    return parse_rules(data)