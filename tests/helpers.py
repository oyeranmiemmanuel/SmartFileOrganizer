"""Shared helpers for tests. All files live under pytest's tmp_path."""

from __future__ import annotations

import os
from pathlib import Path


def make_tree(base: Path, names: list[str] | dict[str, bytes]) -> None:
    """Create disposable files. ``names`` are forward-slash relative paths."""
    items = names.items() if isinstance(names, dict) else ((n, b"x") for n in names)
    for relative, content in items:
        path = base.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def snapshot(base: Path) -> dict[str, tuple[str, int, int]]:
    """Every file and folder under ``base`` with size and mtime, to prove nothing changed."""
    state: dict[str, tuple[str, int, int]] = {}
    for root, dirs, files in os.walk(base):
        for name in dirs:
            path = Path(root, name)
            state[str(path.relative_to(base))] = ("dir", 0, 0)
        for name in files:
            path = Path(root, name)
            info = path.stat()
            state[str(path.relative_to(base))] = ("file", info.st_size, info.st_mtime_ns)
    return state


def build_plan_for(tmp_path, names, *, recursive=False, **option_kwargs):
    """Create ``source`` with ``names`` and return (source, destination, plan)."""
    from organizer.categories import default_rules
    from organizer.planner import PlanOptions, build_plan
    from organizer.scanner import scan_directory

    source = tmp_path / "source"
    source.mkdir(parents=True, exist_ok=True)
    make_tree(source, names)
    destination = tmp_path / "source_Organized"
    rules = default_rules()
    scan = scan_directory(source, recursive=recursive, rules=rules)
    return source, destination, build_plan(scan, rules, destination, PlanOptions(**option_kwargs))
