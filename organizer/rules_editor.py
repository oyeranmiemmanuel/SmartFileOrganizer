"""Editing the user's rules file safely.

The file is an "overlay" on the built-in defaults (see categories.py): it lists
only what the user changed. These functions change that overlay as a plain
dictionary; the caller validates it with ``parse_rules`` before saving, so a
bad edit can never reach the disk.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .categories import (
    NO_EXTENSION_CATEGORY,
    UNKNOWN_CATEGORY,
    RulesError,
    default_rules,
    rules_template,
)

_DEFAULTS = default_rules()


def new_overlay() -> dict[str, Any]:
    return rules_template()


def load_overlay(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read the rules file as a dictionary. A missing file gives an empty overlay."""
    file_path = Path(path)
    if not file_path.exists():
        return new_overlay()
    try:
        text = file_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise RulesError(f"Could not read rules file '{file_path}': {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RulesError(
            f"Rules file '{file_path}' is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}"
        ) from exc
    if not isinstance(data, dict):
        raise RulesError("The rules file must contain a JSON object.")
    return data


def save_overlay(path: str | os.PathLike[str], overlay: dict[str, Any]) -> None:
    """Write the overlay, replacing the old file only after a complete write."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp = file_path.with_name(file_path.name + ".tmp")
    temp.write_text(json.dumps(overlay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, file_path)


def backup_file(path: str | os.PathLike[str]) -> Path | None:
    """Copy ``path`` to ``path.bak`` (replacing an older backup). None if there is no file."""
    file_path = Path(path)
    if not file_path.exists():
        return None
    backup = file_path.with_name(file_path.name + ".bak")
    shutil.copy2(file_path, backup)
    return backup


def _section(overlay: dict[str, Any], key: str, kind: type) -> Any:
    value = overlay.get(key)
    if not isinstance(value, kind):
        value = kind()
        overlay[key] = value
    return value


def _normalize_extension(extension: str) -> str:
    cleaned = extension.strip().lower()
    if not cleaned.strip("."):
        return ""
    return "." + cleaned.lstrip(".")


def _drop_extension_keys(section: dict[str, Any], extension: str) -> None:
    for key in list(section):
        if _normalize_extension(str(key)) == extension:
            del section[key]


def set_extension_category(overlay: dict[str, Any], extension: str, category: str) -> None:
    """Send ``extension`` to ``category`` (an existing category or a new name)."""
    ext = _normalize_extension(extension)
    if not ext:
        raise ValueError(
            "Files without an extension use the 'No Extension' folder. Rename that folder instead."
        )
    name = category.strip()
    if not name:
        raise ValueError("The category name cannot be empty.")
    section = _section(overlay, "extension_overrides", dict)
    _drop_extension_keys(section, ext)
    if _DEFAULTS.extension_map.get(ext) != name:  # no override needed if it matches the default
        section[ext] = name


def clear_extension_override(overlay: dict[str, Any], extension: str) -> None:
    section = overlay.get("extension_overrides")
    if isinstance(section, dict):
        _drop_extension_keys(section, _normalize_extension(extension))


def set_category_folder(overlay: dict[str, Any], category: str, folder: str) -> None:
    """Use ``folder`` as the destination folder name for ``category``."""
    name = folder.strip()
    if not name:
        raise ValueError("The folder name cannot be empty.")
    if category == UNKNOWN_CATEGORY:
        overlay["unknown_folder"] = name
    elif category == NO_EXTENSION_CATEGORY:
        overlay["no_extension_folder"] = name
    else:
        section = _section(overlay, "folder_names", dict)
        if name == category:
            section.pop(category, None)
        else:
            section[category] = name


def clear_category_folder(overlay: dict[str, Any], category: str) -> None:
    """Go back to the built-in folder name for ``category``."""
    if category == UNKNOWN_CATEGORY:
        overlay.pop("unknown_folder", None)
    elif category == NO_EXTENSION_CATEGORY:
        overlay.pop("no_extension_folder", None)
    else:
        section = overlay.get("folder_names")
        if isinstance(section, dict):
            section.pop(category, None)


def add_keyword_rule(overlay: dict[str, Any], keyword: str, folder: str) -> None:
    """Files whose NAME contains ``keyword`` go to ``folder``. Replaces a rule with the same keyword."""
    word, destination = keyword.strip(), folder.strip()
    if not word:
        raise ValueError("The keyword cannot be empty.")
    if not destination:
        raise ValueError("The folder name cannot be empty.")
    rules = _section(overlay, "keyword_rules", list)
    for entry in rules:
        if isinstance(entry, dict) and str(entry.get("keyword", "")).strip().casefold() == word.casefold():
            entry["keyword"], entry["folder"] = word, destination
            return
    rules.append({"keyword": word, "folder": destination})


def remove_keyword_rule(overlay: dict[str, Any], keyword: str) -> None:
    rules = overlay.get("keyword_rules")
    if isinstance(rules, list):
        needle = keyword.strip().casefold()
        overlay["keyword_rules"] = [
            entry for entry in rules
            if not (isinstance(entry, dict) and str(entry.get("keyword", "")).strip().casefold() == needle)
        ]