"""btop.conf reading and writing (key = value lines, '#' comments, quoted strings, True/False bools)."""

from __future__ import annotations

import os
import re
from typing import Any

CONFIG_LINE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$")


def config_dir() -> str:
    """$XDG_CONFIG_HOME/pybtop, falling back to ~/.config/pybtop.

    A separate directory keeps this clone from overwriting btop's own ~/.config/btop/btop.conf.
    """
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "pybtop")


def config_path() -> str:
    return os.path.join(config_dir(), "btop.conf")


def parse_value(raw: str) -> Any:
    """Interpret one raw right-hand side. Quoted text is a string; True/False are bools; digits are ints."""
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1]
    if raw in ("True", "False"):
        return raw == "True"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return str(value)
    return f'"{value}"'


def parse_config_text(text: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = CONFIG_LINE.match(stripped)
        if match:
            values[match.group(1)] = parse_value(match.group(2))
    return values


def load_config(path: str | None = None) -> dict[str, Any]:
    path = path or config_path()
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return parse_config_text(fh.read())
    except OSError:
        return {}


def merge_config_lines(old_lines: list[str], values: dict[str, Any]) -> list[str]:
    """Apply `values` to an existing file's lines, keeping comments, blank lines and unknown keys.

    A key whose value changed is rewritten in place; unchanged lines are kept byte-for-byte. A key
    missing from the file is inserted after the nearest earlier key (in `values` order) that is
    present, or before the first key line when none is.
    """
    order = list(values)
    lines = list(old_lines)
    present: set[str] = set()
    for idx, line in enumerate(lines):
        match = CONFIG_LINE.match(line)
        if not match or match.group(1) not in values:
            continue
        key = match.group(1)
        present.add(key)
        current = parse_value(match.group(2))
        if type(current) is not type(values[key]) or current != values[key]:
            lines[idx] = f"{key} = {format_value(values[key])}"

    def key_line(key: str) -> int | None:
        for idx, line in enumerate(lines):
            match = CONFIG_LINE.match(line)
            if match and match.group(1) == key:
                return idx
        return None

    for key in order:
        if key in present:
            continue
        new_line = f"{key} = {format_value(values[key])}"
        anchor = None
        for prev in reversed(order[: order.index(key)]):
            anchor = key_line(prev)
            if anchor is not None:
                break
        if anchor is not None:
            lines.insert(anchor + 1, new_line)
        else:
            first = next((i for i, line in enumerate(lines) if CONFIG_LINE.match(line)), len(lines))
            lines.insert(first, new_line)
        present.add(key)
    return lines


def write_config(values: dict[str, Any], path: str | None = None) -> None:
    path = path or config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            old_lines = fh.read().splitlines()
    except OSError:
        old_lines = []
    lines = merge_config_lines(old_lines, values)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


class Config:
    """Typed view over a defaults dict overlaid with values from btop.conf."""

    def __init__(self, defaults: dict[str, Any], overrides: dict[str, Any] | None = None) -> None:
        self.defaults = dict(defaults)
        self.values = dict(defaults)
        for key, val in (overrides or {}).items():
            if key in self.defaults and type(val) is type(self.defaults[key]):
                self.values[key] = val

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in self.defaults:
            raise KeyError(key)
        self.values[key] = value

    def get_bool(self, key: str) -> bool:
        return bool(self.values[key])

    def get_int(self, key: str) -> int:
        return int(self.values[key])

    def get_str(self, key: str) -> str:
        return str(self.values[key])
