"""Drawing helpers shared by the overlays: rounded or plain boxes and title buttons."""

from __future__ import annotations

from ..render.ansi import Canvas, Color

ROUND = {"tl": "╭", "tr": "╮", "bl": "╰", "br": "╯"}
PLAIN = {"tl": "┌", "tr": "┐", "bl": "└", "br": "┘"}


def draw_box(canvas: Canvas, row: int, col: int, height: int, width: int, color: Color, rounded: bool) -> None:
    """Draw a border around the given rectangle (0-based, inclusive of the border)."""
    if height < 2 or width < 2:
        return
    corners = ROUND if rounded else PLAIN
    canvas.put(row, col, corners["tl"] + "─" * (width - 2) + corners["tr"], fg=color)
    for r in range(row + 1, row + height - 1):
        canvas.put(r, col, "│", fg=color)
        canvas.put(r, col + width - 1, "│", fg=color)
    canvas.put(row + height - 1, col, corners["bl"] + "─" * (width - 2) + corners["br"], fg=color)


def draw_title_buttons(
    canvas: Canvas,
    row: int,
    col: int,
    width: int,
    border: Color,
    buttons: list[tuple[str, Color | None, bool]],
    start: int = 2,
    align_right: bool = False,
) -> None:
    """Overlay '┐label┌' buttons on a top or bottom border row.

    `buttons` items are (label, color, bold). With align_right the group ends two cells before the
    right corner, mirroring btop's right-hand header controls.
    """
    segments: list[tuple[str, Color | None, bool]] = []
    for label, colour, bold in buttons:
        segments.append(("┐", border, False))
        segments.append((label, colour, bold))
        segments.append(("┌", border, False))
    total = sum(len(text) for text, _, _ in segments)
    x = col + width - 2 - total if align_right else col + start
    for text, colour, bold in segments:
        if x >= col + width - 1:
            break
        canvas.put(row, x, text, fg=colour, bold=bold)
        x += len(text)


def text(canvas: Canvas, row: int, col: int, value: str, color: Color = None, bold: bool = False) -> None:
    canvas.put(row, col, value, fg=color, bold=bold)
