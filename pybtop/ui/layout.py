"""Box geometry for the main screen, matching btop 1.3.0's calcSizes (GPU build, default config).

Rules come from btop's src/btop_draw.cpp Draw::calcSizes (see files/src-notes/layout_rules.md).
Coordinates are 0-based; btop's 1-based x/y values are converted here.
"""

from __future__ import annotations

import math
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


def cpu_height(total_rows: int, gpu_count: int = 0) -> int:
    """CPU box rows: max(8, ceil(H*32/100)), plus one row per GPU when it fits."""
    base = max(8, math.ceil(total_rows * 32 / 100))
    return base + gpu_count if base <= total_rows - gpu_count else base


def compute(width: int, height: int, gpu_count: int = 0) -> dict[str, Rect]:
    """Default-config rectangles for cpu, mem, net and proc."""
    cpu_h = cpu_height(height, gpu_count)
    left_w = c_round(width * 45 / 100)
    split_row = math.ceil(height * 68 / 100)  # first row below the MEM+NET stack
    return {
        "cpu": Rect(0, 0, cpu_h, width),
        "mem": Rect(cpu_h, 0, split_row - cpu_h, left_w),
        "net": Rect(split_row, 0, height - split_row, left_w),
        "proc": Rect(cpu_h, left_w, height - cpu_h, width - left_w),
    }


def fits(width: int, height: int) -> bool:
    return width >= MIN_WIDTH and height >= MIN_HEIGHT
