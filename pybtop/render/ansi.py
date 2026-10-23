"""Terminal output primitives: ANSI sequences, colors, a cell canvas and graph symbols."""

from __future__ import annotations

from dataclasses import dataclass

RESET = "\x1b[0m"


def fg_rgb(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


def bg_rgb(r: int, g: int, b: int) -> str:
    return f"\x1b[48;2;{r};{g};{b}m"


def fg_256(n: int) -> str:
    return f"\x1b[38;5;{n}m"


def bg_256(n: int) -> str:
    return f"\x1b[48;5;{n}m"


def move(row: int, col: int) -> str:
    """1-based cursor position."""
    return f"\x1b[{row};{col}H"


@dataclass(frozen=True)
class Ansi16:
    """A basic terminal colour: 0-7 normal, 8-15 bright. Emitted as an SGR code, never as RGB."""

    index: int


Color = tuple[int, int, int] | Ansi16 | None  # None means terminal default


def ansi16_sequence(color: Ansi16, background: bool) -> str:
    base = (40 if background else 30) if color.index < 8 else (100 if background else 90)
    return f"\x1b[{base + color.index % 8}m"


def parse_color(text: str) -> Color:
    """Parse a btop theme color: '#RRGGBB', '#BW' (hex gray), or 'R G B' decimal. Empty -> default."""
    text = text.strip()
    if not text:
        return None
    if text.startswith("#"):
        hexpart = text[1:]
        if len(hexpart) == 2:
            v = int(hexpart, 16)
            return (v, v, v)
        if len(hexpart) == 6:
            return (int(hexpart[0:2], 16), int(hexpart[2:4], 16), int(hexpart[4:6], 16))
        raise ValueError(f"bad hex color: {text!r}")
    parts = text.split()
    if len(parts) == 3:
        r, g, b = (int(p) for p in parts)
        return (r, g, b)
    raise ValueError(f"bad color: {text!r}")


def lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def gradient_color(stops: list[Color], percent: float) -> Color:
    """Map 0..100 onto a list of color stops (2 stops: start..end; 3 stops: start..mid..end)."""
    if len(stops) == 1:
        return stops[0]
    if isinstance(stops[0], Ansi16):
        # btop's TTY theme has no gradient interpolation: it switches stops at 50 (two stops)
        # or at 33 and 66 (three stops), using the integer percent.
        p = int(max(0.0, min(100.0, percent)) + 0.5)
        if len(stops) == 2:
            return stops[0] if p <= 50 else stops[1]
        return stops[0] if p <= 33 else stops[1] if p <= 66 else stops[2]
    t = max(0.0, min(100.0, percent)) / 100.0
    if len(stops) == 2:
        return lerp_color(stops[0], stops[1], t)
    if t <= 0.5:
        return lerp_color(stops[0], stops[1], t * 2)
    return lerp_color(stops[1], stops[2], (t - 0.5) * 2)


@dataclass
class Cell:
    char: str = " "
    fg: Color = None
    bg: Color = None
    bold: bool = False


class Canvas:
    """A width x height grid of cells that is serialized with minimal cursor movement."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.cells = [[Cell() for _ in range(width)] for _ in range(height)]

    def put(self, row: int, col: int, text: str, fg: Color = None, bg: Color = None, bold: bool = False) -> None:
        """Write text at 0-based (row, col), clipping at the right edge.

        A None background keeps whatever background the cell already has, so text drawn over a
        filled row or a themed main background stays on that background.
        """
        if not (0 <= row < self.height):
            return
        for i, ch in enumerate(text):
            x = col + i
            if x < 0:
                continue
            if x >= self.width:
                break
            cell_bg = bg if bg is not None else self.cells[row][x].bg
            self.cells[row][x] = Cell(ch, fg, cell_bg, bold)

    def fill_rect(self, row: int, col: int, height: int, width: int, bg: Color) -> None:
        for r in range(row, min(row + height, self.height)):
            for c in range(col, min(col + width, self.width)):
                cell = self.cells[r][c]
                self.cells[r][c] = Cell(cell.char, cell.fg, bg, cell.bold)

    def render(self, low_color: bool = False) -> str:
        """Full-screen frame as one string (cursor home, then each row, no trailing newline)."""
        out: list[str] = ["\x1b[H"]
        for r, row in enumerate(self.cells):
            out.append(move(r + 1, 1))
            last_style: tuple = ("__init__",)
            for cell in row:
                style = (cell.fg, cell.bg, cell.bold)
                if style != last_style:
                    out.append(_style_sequence(cell, low_color))
                    last_style = style
                out.append(cell.char)
            out.append(RESET)
        return "".join(out)


def rgb_to_256(rgb: tuple[int, int, int]) -> int:
    """Nearest entry in the xterm 6x6x6 colour cube (indices 16..231)."""
    r, g, b = (round(c * 5 / 255) for c in rgb)
    return 16 + 36 * r + 6 * g + b


def _style_sequence(cell: Cell, low_color: bool = False) -> str:
    parts = [RESET]
    if cell.bold:
        parts.append("\x1b[1m")
    if cell.fg is not None:
        parts.append(_color_sequence(cell.fg, False, low_color))
    if cell.bg is not None:
        parts.append(_color_sequence(cell.bg, True, low_color))
    return "".join(parts)


def _color_sequence(color: Color, background: bool, low_color: bool) -> str:
    if isinstance(color, Ansi16):
        return ansi16_sequence(color, background)
    if background:
        return bg_256(rgb_to_256(color)) if low_color else bg_rgb(*color)
    return fg_256(rgb_to_256(color)) if low_color else fg_rgb(*color)
