"""Box geometry for the main screen, matching btop 1.3.0's calcSizes (GPU build).

Rules come from btop's src/btop_draw.cpp Draw::calcSizes (see files/src-notes/layout_rules.md).
Coordinates are 0-based; btop's 1-based x/y values are converted here.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

MIN_WIDTH = 80
MIN_HEIGHT = 24


def c_round(value: float) -> int:
    """C round(): half away from zero (Python's round() is half-to-even)."""
    return int(math.floor(value + 0.5)) if value >= 0 else -int(math.floor(-value + 0.5))


@dataclass(frozen=True)
class Rect:
    row: int
    col: int
    height: int
    width: int

    @property
    def inner(self) -> "Rect":
        return Rect(self.row + 1, self.col + 1, max(0, self.height - 2), max(0, self.width - 2))


BOXES = ("cpu", "mem", "net", "proc")
CPU_HEIGHT_PCT = 32
NET_HEIGHT_PCT = 32
SIDE_WIDTH_PCT = 45  # MEM and NET width when PROC is shown


def cpu_height(total_rows: int, gpu_count: int = 0, only_cpu: bool = False) -> int:
    """CPU box rows: max(8, ceil(H*32/100)) (all of H when CPU is the only box), plus one row per GPU when it fits."""
    base = max(8, math.ceil(total_rows * (100 if only_cpu else CPU_HEIGHT_PCT) / 100))
    return base + gpu_count if base <= total_rows - gpu_count else base


def compute(
    width: int,
    height: int,
    gpu_count: int = 0,
    shown: Iterable[str] = BOXES,
    cpu_bottom: bool = False,
    proc_left: bool = False,
    mem_below_net: bool = False,
) -> dict[str, Rect]:
    """Rectangles for the shown boxes, following btop's Draw::calcSizes (GPU build).

    Hidden boxes take no space: the remaining boxes re-flow into the freed rows and columns.
    """
    shown = set(shown)
    cpu_on, mem_on, net_on, proc_on = (name in shown for name in BOXES)
    cpu_h = cpu_height(height, gpu_count, only_cpu=shown == {"cpu"}) if cpu_on else 0
    side_w = c_round(width * (SIDE_WIDTH_PCT if proc_on else 100) / 100)
    mem_h = math.ceil(height * (100 - NET_HEIGHT_PCT * net_on) / 100) - cpu_h if mem_on else 0
    net_h = height - cpu_h - mem_h if net_on else 0
    side_col = width - side_w if proc_left and proc_on else 0

    rects: dict[str, Rect] = {}
    if cpu_on:
        rects["cpu"] = Rect(height - cpu_h if cpu_bottom else 0, 0, cpu_h, width)
    if mem_on:
        if mem_below_net and net_on:
            row = height - mem_h - (cpu_h if cpu_bottom else 0)
        else:
            row = 0 if cpu_bottom else cpu_h
        rects["mem"] = Rect(row, side_col, mem_h, side_w)
    if net_on:
        if mem_below_net and mem_on:
            row = 0 if cpu_bottom else cpu_h
        else:
            row = height - net_h - (cpu_h if cpu_bottom else 0)
        rects["net"] = Rect(row, side_col, net_h, side_w)
    if proc_on:
        proc_w = width - (side_w if mem_on or net_on else 0)
        row = 0 if cpu_bottom and cpu_on else cpu_h
        col = 0 if proc_left else width - proc_w
        rects["proc"] = Rect(row, col, height - cpu_h, proc_w)
    return rects


def fits(width: int, height: int) -> bool:
    return width >= MIN_WIDTH and height >= MIN_HEIGHT
