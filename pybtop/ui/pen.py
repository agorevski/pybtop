"""btop-equivalent drawing core: a cursor-based pen (1-based like btop's Mv::to), createBox,
Meter and Graph, ported from btop 1.3.0 btop_draw.cpp / btop_tools.cpp (see docs/REVERSE_ENGINEERING.md).

All coordinates passed to Pen.to() are btop's 1-based (row, column) values.
"""

from __future__ import annotations

import math

from ..render.ansi import Canvas, Cell, Color, gradient_color
from ..textsafe import printable

H_LINE = "─"
V_LINE = "│"
DIV_LEFT = "├"
DIV_RIGHT = "┤"
DIV_UP = "┬"
DIV_DOWN = "┴"
LEFT_UP, RIGHT_UP, LEFT_DOWN, RIGHT_DOWN = "┌", "┐", "└", "┘"
ROUND_LEFT_UP, ROUND_RIGHT_UP, ROUND_LEFT_DOWN, ROUND_RIGHT_DOWN = "╭", "╮", "╰", "╯"
TITLE_LEFT, TITLE_RIGHT = "┐", "┌"
TITLE_LEFT_DOWN, TITLE_RIGHT_DOWN = "┘", "└"
METER = "■"
SUPERSCRIPT = "⁰¹²³⁴⁵⁶⁷⁸⁹"
GRAPH_BG = "⣀"

# btop's braille table: index = left_level * 5 + right_level (levels 0-4).
BRAILLE_UP = [
    " ", "⢀", "⢠", "⢰", "⢸",
    "⡀", "⣀", "⣠", "⣰", "⣸",
    "⡄", "⣄", "⣤", "⣴", "⣼",
    "⡆", "⣆", "⣦", "⣶", "⣾",
    "⡇", "⣇", "⣧", "⣷", "⣿",
]


def c_round(value: float) -> int:
    """C round(): half away from zero."""
    return int(math.floor(value + 0.5)) if value >= 0 else -int(math.floor(-value + 0.5))


def ljust(text: str, width: int) -> str:
    """btop ljust with truncation: pad on the right, cut to width."""
    return text[:width].ljust(width)


def rjust(text: str, width: int) -> str:
    """btop rjust with truncation: pad on the left, cut to width."""
    return text[:width].rjust(width) if len(text) <= width else text[:width]


def cjust(text: str, width: int) -> str:
    if len(text) >= width:
        return text[:width]
    pad = width - len(text)
    return " " * math.ceil(pad / 2) + text + " " * (pad // 2)


def uresize(text: str, width: int) -> str:
    """btop uresize: truncate to width characters (no padding)."""
    return text[:max(0, width)]


class Pen:
    """Cursor and style state over a Canvas. Coordinates are btop's 1-based values."""

    def __init__(self, canvas: Canvas) -> None:
        self.canvas = canvas
        self.y = 1
        self.x = 1
        self.fg: Color = None
        self.bg: Color = None
        self.bold = False

    def to(self, y: int, x: int) -> None:
        self.y, self.x = self._clamp(y, x)

    def _clamp(self, y: int, x: int) -> tuple[int, int]:
        """Terminals clamp cursor moves to the screen; btop relies on that at the left border."""
        return max(1, min(self.canvas.height, y)), max(1, min(self.canvas.width, x))

    def r(self, n: int) -> None:
        self.x = self._clamp(self.y, self.x + max(1, n))[1]  # btop emits ESC[0C for n == 0, which moves one cell

    def l(self, n: int) -> None:
        self.x = self._clamp(self.y, self.x - max(1, n))[1]

    def u(self, n: int) -> None:
        self.y = self._clamp(self.y - max(1, n), self.x)[0]

    def d(self, n: int) -> None:
        self.y = self._clamp(self.y + max(1, n), self.x)[0]

    def style(self, fg: Color = None, bold: bool | None = None, bg: Color | None = None) -> None:
        if fg is not None:
            self.fg = fg
        if bold is not None:
            self.bold = bold
        if bg is not None:
            self.bg = bg

    def write(self, text: str, fg: Color | None = None, bold: bool | None = None) -> None:
        if fg is not None or bold is not None:
            self.style(fg=fg, bold=bold)
        for ch in printable(text):
            row, col = self.y - 1, self.x - 1
            if 0 <= row < self.canvas.height and 0 <= col < self.canvas.width:
                cell_bg = self.bg if self.bg is not None else self.canvas.cells[row][col].bg
                self.canvas.cells[row][col] = Cell(ch, self.fg, cell_bg, self.bold)
            self.x += 1

    def skip_cells(self, count: int) -> None:
        self.r(count)


def create_box(
    pen: Pen,
    x: int,
    y: int,
    width: int,
    height: int,
    line_color: Color,
    fill: bool,
    title: str = "",
    title2: str = "",
    num: int = 0,
    rounded: bool = True,
    title_color: Color = None,
    hi_color: Color = None,
    bg: Color = None,
) -> None:
    """Port of btop createBox: borders, corners, superscript number and titles (1-based x/y)."""
    pen.style(bg=bg)
    pen.style(fg=line_color, bold=False)
    for hpos in (y, y + height - 1):
        pen.to(hpos, x)
        pen.write(H_LINE * (width - 1), fg=line_color)
    for hpos in range(y + 1, y + height - 1):
        pen.to(hpos, x)
        pen.write(V_LINE, fg=line_color)
        if fill:
            pen.write(" " * (width - 2), fg=line_color)
        else:
            pen.r(width - 2)
        pen.write(V_LINE, fg=line_color)
    corners = (
        (ROUND_LEFT_UP, ROUND_RIGHT_UP, ROUND_LEFT_DOWN, ROUND_RIGHT_DOWN)
        if rounded
        else (LEFT_UP, RIGHT_UP, LEFT_DOWN, RIGHT_DOWN)
    )
    pen.to(y, x)
    pen.write(corners[0], fg=line_color)
    pen.to(y, x + width - 1)
    pen.write(corners[1], fg=line_color)
    pen.to(y + height - 1, x)
    pen.write(corners[2], fg=line_color)
    pen.to(y + height - 1, x + width - 1)
    pen.write(corners[3], fg=line_color)

    numbering = ""
    if num:
        numbering = SUPERSCRIPT[max(0, min(num, 9))]
    if title:
        pen.to(y, x + 2)
        pen.write(TITLE_LEFT, fg=line_color)
        if hi_color is not None and numbering:
            pen.write(numbering, fg=hi_color, bold=True)
        pen.write(title, fg=title_color or line_color, bold=True)
        pen.write(TITLE_RIGHT, fg=line_color, bold=False)
    if title2:
        pen.to(y + height - 1, x + 2)
        pen.write(TITLE_LEFT_DOWN, fg=line_color)
        if hi_color is not None and numbering:
            pen.write(numbering, fg=hi_color, bold=True)
        pen.write(title2, fg=title_color or line_color, bold=True)
        pen.write(TITLE_RIGHT_DOWN, fg=line_color, bold=False)


def meter(
    pen: Pen, value: float, width: int, gradient: list[tuple[int, int, int]], meter_bg: Color, invert: bool = False
) -> None:
    """Port of btop Meter: `width` cells of ■, coloured by the gradient at each cell's percent (inverted: 100 - percent)."""
    if width < 1:
        return
    value = max(0.0, min(100.0, value))
    for i in range(1, width + 1):
        y = c_round(i * 100.0 / width)
        if value >= y:
            pen.write(METER, fg=gradient_color(gradient, 100 - y if invert else y))
        else:
            pen.write(METER * (width + 1 - i), fg=meter_bg)
            break


def _level(value: float, cur_high: int, cur_low: int, mod: float, clamp_min: int) -> int:
    if value >= cur_high:
        return 4
    if value <= cur_low:
        return clamp_min
    scaled = c_round((value - cur_low) * 4 / (cur_high - cur_low) + mod)
    return max(clamp_min, min(4, scaled))


def graph_rows(
    values: list[float],
    width: int,
    height: int,
    no_zero: bool = True,
    invert: bool = False,
) -> list[str]:
    """Braille (or single-row) graph glyph rows, top row first, as btop's Graph::operator builds them.

    Each cell encodes two samples (left, right). The newest sample is the last value.
    `invert` mirrors the graph vertically (used for the lower CPU graph).
    """
    if width <= 0 or height <= 0:
        return []
    mod = 0.3 if height == 1 else 0.1
    need = 2 * width
    window: list[float | None] = list(values[-need:])
    window = [None] * (need - len(window)) + window
    rows: list[str] = []
    for horizon in range(height):
        cur_high = c_round(100 * (height - horizon) / height)
        cur_low = c_round(100 * (height - (horizon + 1)) / height)
        clamp_min = 1 if (no_zero and horizon == height - 1) else 0
        line = []
        for col in range(width):
            left_v, right_v = window[2 * col], window[2 * col + 1]
            if left_v is None and right_v is None:
                line.append(" ")
                continue
            left = _level(left_v or 0.0, cur_high, cur_low, mod, clamp_min)
            right = _level(right_v or 0.0, cur_high, cur_low, mod, clamp_min)
            line.append(BRAILLE_UP[left * 5 + right])
        rows.append("".join(line))
    if invert:
        rows = [_mirror_rows(line) for line in reversed(rows)]
    return rows


def _mirror_rows(line: str) -> str:
    """Vertically mirror each braille glyph in a row (btop's _down symbol table for inverted graphs)."""
    return "".join(_mirror_glyph(ch) for ch in line)


_MIRROR_PAIRS = ((0x01, 0x40), (0x08, 0x80), (0x02, 0x04), (0x10, 0x20))


def _mirror_glyph(ch: str) -> str:
    code = ord(ch) - 0x2800
    if not (0 <= code <= 0xFF) or ch == " ":
        return ch
    for a, b in _MIRROR_PAIRS:
        bit_a, bit_b = bool(code & a), bool(code & b)
        code &= ~(a | b)
        if bit_a:
            code |= b
        if bit_b:
            code |= a
    return chr(0x2800 + code)


def graph(
    pen: Pen,
    values: list[float],
    width: int,
    height: int,
    gradient: list[tuple[int, int, int]],
    no_zero: bool = True,
    invert: bool = False,
) -> None:
    """Draw a graph with its top-left at the pen's position.

    As in btop, the cursor is left on the bottom row, one column past the graph's right edge.
    """
    if width <= 0 or height <= 0:
        return
    rows = graph_rows(values, width, height, no_zero, invert)
    window: list[float | None] = list(values[-2 * width:])
    window = [None] * (2 * width - len(window)) + window
    top_y, left_x = pen.y, pen.x
    for idx, line in enumerate(rows):
        pen.to(top_y + idx, left_x)
        for col, ch in enumerate(line):
            if ch == " ":
                pen.r(1)
                continue
            present = [v for v in window[2 * col : 2 * col + 2] if v is not None]
            pen.write(ch, fg=gradient_color(gradient, max(present) if present else 0.0))
    pen.to(top_y + height - 1, left_x + width)
