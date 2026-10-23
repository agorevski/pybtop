"""Theme loading: btop's theme[key]="value" files plus the built-in Default and TTY themes."""

from __future__ import annotations

import os
import re

from .render.ansi import Color, parse_color

SYSTEM_THEME_DIR = "/usr/share/btop/themes"
THEME_LINE = re.compile(r'^\s*theme\[([a-z_0-9]+)\]\s*=\s*(?:"([^"]*)"|(\S+))')

# Gradient keys are three-stop (start/mid/end); a stop left empty collapses the gradient.
GRADIENT_PREFIXES = (
    "cpu", "proc", "temp", "free", "cached", "available", "used", "download", "upload",
    "process",
)

# Built-in Default theme. Values come from the btop 1.3.0 binary's literal table and were
# checked against rendered cells (see docs/REVERSE_ENGINEERING.md, "Configuration").
DEFAULT_THEME: dict[str, str] = {
    "main_bg": "#000000",
    "main_fg": "#cccccc",
    "title": "#eeeeee",
    "hi_fg": "#b54040",
    "selected_bg": "#6a2f2f",
    "selected_fg": "#eeeeee",
    "inactive_fg": "#404040",
    "graph_text": "#606060",
    "meter_bg": "#404040",
    "proc_misc": "#0de756",
    "cpu_box": "#556d59",
    "mem_box": "#6c6c4b",
    "net_box": "#5c588d",
    "proc_box": "#805252",
    "div_line": "#303030",
    "temp_start": "#4897d4",
    "temp_mid": "#5474e8",
    "temp_end": "#ff40b6",
    "cpu_start": "#77ca9b",
    "cpu_mid": "#cbc06c",
    "cpu_end": "#dc4c4c",
    "free_start": "#384f21",
    "free_mid": "#b5e685",
    "free_end": "#dcff85",
    "cached_start": "#163350",
    "cached_mid": "#74e6fc",
    "cached_end": "#26c5ff",
    "available_start": "#4e3f0e",
    "available_mid": "#ffd77a",
    "available_end": "#ffb814",
    "used_start": "#592b26",
    "used_mid": "#d9626d",
    "used_end": "#ff4769",
    "download_start": "#291f75",
    "download_mid": "#4f43a3",
    "download_end": "#b0a9de",
    "upload_start": "#620665",
    "upload_mid": "#7d4180",
    "upload_end": "#dcafde",
    "process_start": "#80d0a3",
    "process_mid": "#dcd179",
    "process_end": "#d45454",
}


class Theme:
    """Resolved colors. Each key maps to a Color (RGB tuple or None for terminal default)."""

    def __init__(self, raw: dict[str, str]) -> None:
        self.raw = raw

    def color(self, key: str) -> Color:
        return parse_color(self.raw.get(key, DEFAULT_THEME.get(key, "")))

    def gradient(self, prefix: str) -> list[tuple[int, int, int]]:
        """Stops for a gradient, e.g. 'cpu' -> [start, mid, end] with empties dropped."""
        stops = []
        for suffix in ("start", "mid", "end"):
            c = self.color(f"{prefix}_{suffix}")
            if c is not None:
                stops.append(c)
        return stops or [(255, 255, 255)]


def parse_theme_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = THEME_LINE.match(line)
        if match:
            # Quoted values use the text up to the first closing quote; trailing junk is ignored.
            values[match.group(1)] = match.group(2) if match.group(2) is not None else match.group(3)
    return values


def find_theme_file(name: str, user_dir: str, system_dir: str = SYSTEM_THEME_DIR) -> str | None:
    """User themes override system themes. Names are bare file names without '.theme'."""
    for directory in (user_dir, system_dir):
        candidate = os.path.join(directory, f"{name}.theme")
        if os.path.isfile(candidate):
            return candidate
    return None


def load_theme(name: str, user_dir: str, system_dir: str = SYSTEM_THEME_DIR) -> Theme:
    if name in ("", "Default"):
        return Theme({})
    if name == "TTY":
        return Theme({})
    path = find_theme_file(name, user_dir, system_dir)
    if path is None:
        return Theme({})
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return Theme(parse_theme_text(fh.read()))
    except OSError:
        return Theme({})


def available_themes(user_dir: str, system_dir: str = SYSTEM_THEME_DIR) -> list[str]:
    names = {"Default", "TTY"}
    for directory in (user_dir, system_dir):
        try:
            for entry in os.listdir(directory):
                if entry.endswith(".theme"):
                    names.add(entry[: -len(".theme")])
        except OSError:
            continue
    return sorted(names, key=lambda n: (n not in ("Default", "TTY"), n.lower()))
