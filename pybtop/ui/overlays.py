"""Overlay screens: help (verbatim from btop 1.3.0), options, menu, prompts, and the size warning."""

from __future__ import annotations

from ..render.ansi import Canvas
from .draw import draw_box, draw_title_buttons, text
from .palette import Palette

BOX_W = 78
MENU_ITEMS = ["Options", "Help", "Quit"]

# Verbatim help pages from btop 1.3.0 (inner text, box borders removed).
HELP_PAGE_1 = [
    "        Key:        Description:",
    "       Mouse 1      Clicks buttons and selects in process list.",
    "    Mouse scroll    Scrolls any scrollable list/text under cursor.",
    "       Esc, m       Toggles main menu.",
    "          p         Cycle view presets forwards.",
    "      shift + p     Cycle view presets backwards.",
    "          1         Toggle CPU box.",
    "          2         Toggle MEM box.",
    "          3         Toggle NET box.",
    "          4         Toggle PROC box.",
    "          5         Toggle GPU box.",
    "          d         Toggle disks view in MEM box.",
    "        F2, o       Shows options.",
    "      F1, ?, h      Shows this window.",
    "      ctrl + z      Sleep program and put in background.",
    "     q, ctrl + c    Quits program.",
    "        +, -        Add/Subtract 100ms to/from update timer.",
    "      Up, Down      Select in process list.",
    "        Enter       Show detailed information for selected process.",
    "      Spacebar      Expand/collapse the selected process in tree view.",
    "   Pg Up, Pg Down   Jump 1 page in process list.",
    "      Home, End     Jump to first or last page in process list.",
    "     Left, Right    Select previous/next sorting column.",
    "        b, n        Select previous/next network device.",
    "          i         Toggle disks io mode with big graphs.",
    "          z         Toggle totals reset for current network device",
    "          a         Toggle auto scaling for the network graphs.",
    "          y         Toggle synced scaling mode for network graphs.",
    "        f, /        To enter a process filter.",
    "       delete       Clear any entered filter.",
    "          c         Toggle per-core cpu usage of processes.",
    "          r         Reverse sorting order in processes box.",
]

HELP_PAGE_2 = [
    "        Key:        Description:",
    "          e         Toggle processes tree view.",
    "          %         Toggles memory display mode in processes box.",
    "    Selected +, -   Expand/collapse the selected process in tree view.",
    "     Selected t     Terminate selected process with SIGTERM - 15.",
    "     Selected k     Kill selected process with SIGKILL - 9.",
    "     Selected s     Select or enter signal to send to process.",
    "",
    "                    For bug reporting and project updates, visit:",
    "                    https://github.com/aristocratos/btop",
]

HELP_PAGES = [HELP_PAGE_1, HELP_PAGE_2]


def _frame(canvas: Canvas, row: int, col: int, height: int, width: int, pal: Palette, title: str, footer: str) -> None:
    draw_box(canvas, row, col, height, width, pal.box("cpu"), True)
    draw_title_buttons(canvas, row, col, width, pal.box("cpu"), [(title, pal.title, True)], start=2)
    if footer:
        canvas.put(row + height - 1, col + 2, footer, fg=pal.hi_fg)


def center(width: int, screen: int, size: int) -> int:
    return max(0, (screen - size) // 2)


def draw_help(canvas: Canvas, pal: Palette, page: int) -> None:
    lines = HELP_PAGES[min(page, len(HELP_PAGES) - 1)]
    height = 36
    width = BOX_W
    row = center(width, canvas.height, height)
    col = center(width, canvas.width, width)
    footer = f"↑ page {page + 1}/{len(HELP_PAGES)} ↓"
    _frame(canvas, row, col, height, width, pal, "help", footer)
    for i in range(height - 2):
        line = lines[i] if i < len(lines) else ""
        text(canvas, row + 1 + i, col + 1, f"{line:<{width - 2}}"[: width - 2], pal.main_fg)


# Options shown in the overlay. Each entry: (label, config key, kind, choices, description).
OPTIONS = [
    ("Color theme", "color_theme", "theme", None,
     ["Set color theme.", "", "Choose from all theme files in (usually)",
      '"/usr/[local/]share/btop/themes" and', '"~/.config/btop/themes".', "",
      '"Default" for builtin default theme.', '"TTY" for builtin 16-color theme.']),
    ("Theme background", "theme_background", "bool", None,
     ["If the theme set background should be shown.", "",
      "Set to False if you want terminal background", "transparency."]),
    ("Truecolor", "truecolor", "bool", None,
     ["Sets if 24-bit truecolor should be used, will convert", "24-bit colors to 256 color (6x6x6 color cube)", "if false."]),
    ("Force tty", "force_tty", "bool", None,
     ["Force 16-color mode and TTY theme; sets all graph", "symbols to tty."]),
    ("Vim keys", "vim_keys", "bool", None,
     ['Enable "h,j,k,l,g,G" keys for directional control.']),
    ("Rounded corners", "rounded_corners", "bool", None,
     ["Rounded corners on boxes."]),
    ("Graph symbol", "graph_symbol", "choice", ["braille", "block", "tty"],
     ['Default symbols to use for graph creation.']),
    ("Update ms", "update_ms", "int", None,
     ["Update time in milliseconds. Use +/- to change it by 100 ms."]),
    ("Base 10 sizes", "base_10_sizes", "bool", None,
     ["Use base 10 for bits/bytes sizes, KB = 1000 instead of KiB = 1024."]),
    ("Background update", "background_update", "bool", None,
     ["Update main ui in background when menus are showing."]),
    ("Show disks", "show_disks", "bool", None,
     ["If mem box should be split to also show disks info."]),
    ("Mem graphs", "mem_graphs", "bool", None,
     ["Show graphs instead of meters for memory values."]),
    ("Show swap", "show_swap", "bool", None,
     ["If swap memory should be shown in memory box."]),
    ("Process tree", "proc_tree", "bool", None,
     ["Show processes as a tree."]),
    ("Reverse sorting", "proc_reversed", "bool", None,
     ["Reverse sorting order, True or False."]),
    ("Process per core", "proc_per_core", "bool", None,
     ["If process cpu usage should be of the core it's running on", "or usage of the total available cpu power."]),
]


def draw_options(canvas: Canvas, pal: Palette, selected: int, values: dict) -> None:
    width = BOX_W
    height = 32
    row = center(width, canvas.height, height)
    col = center(width, canvas.width, width)
    _frame(canvas, row, col, height, width, pal, "options", "↑ ↓ select  ← → change  esc close")
    left_w = 30
    canvas.put(row + 1, col + 1, "Setting".ljust(left_w), fg=pal.title, bold=True)
    canvas.put(row + 1, col + left_w + 2, "Description", fg=pal.title, bold=True)
    visible = height - 4
    start = max(0, selected - visible // 2)
    for i, (label, key, kind, choices, desc) in enumerate(OPTIONS[start : start + visible]):
        idx = start + i
        r = row + 2 + i
        value = _option_value(values.get(key))
        mark = "›" if idx == selected else " "
        line = f"{mark} {label:<18}{value:>10}"
        fg = pal.selected_fg if idx == selected else pal.main_fg
        bg = pal.selected_bg if idx == selected else None
        if bg is not None:
            canvas.fill_rect(r, col + 1, 1, left_w, bg)
        text(canvas, r, col + 1, line[:left_w].ljust(left_w), fg)
        if idx == selected:
            for j, note in enumerate(desc[: height - 4]):
                text(canvas, row + 2 + j, col + left_w + 3, note[: width - left_w - 6], pal.graph_text)


def _option_value(value: object) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def draw_menu(canvas: Canvas, pal: Palette, selected: int, items: list[str]) -> None:
    width = 30
    height = len(items) + 4
    row = center(width, canvas.height, height)
    col = center(width, canvas.width, width)
    _frame(canvas, row, col, height, width, pal, "menu", "")
    for i, item in enumerate(items):
        selected_row = i == selected
        r = row + 2 + i
        if selected_row:
            canvas.fill_rect(r, col + 1, 1, width - 2, pal.selected_bg)
        text(canvas, r, col + 2, item.ljust(width - 4), pal.selected_fg if selected_row else pal.main_fg)


def draw_prompt(canvas: Canvas, pal: Palette, title: str, lines: list[str]) -> None:
    width = max(len(title), *(len(x) for x in lines)) + 6
    width = min(max(width, 40), canvas.width - 2)
    height = len(lines) + 4
    row = center(width, canvas.height, height)
    col = center(width, canvas.width, width)
    _frame(canvas, row, col, height, width, pal, title, "")
    for i, line in enumerate(lines):
        text(canvas, row + 2 + i, col + 2, line[: width - 4], pal.main_fg)


def draw_too_small(canvas: Canvas, pal: Palette, width: int, height: int, need_w: int, need_h: int) -> None:
    lines = [
        "Terminal size too small:",
        f"  Width = {width} Height = {height}",
        "",
        "Needed for current config:",
        f"  Width = {need_w} Height = {need_h}",
    ]
    top = max(0, (canvas.height - len(lines)) // 2)
    for i, line in enumerate(lines):
        col = max(0, (canvas.width - len(line)) // 2)
        text(canvas, top + i, col, line, pal.main_fg)
