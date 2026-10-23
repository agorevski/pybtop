"""MEM, NET and PROC boxes of btop 1.3.0, ported from Mem::draw (L1107-1356), Net::draw (L1368-1453)
and Proc::draw (L1537-1950) with geometry from Draw::calcSizes (L2123-2237).

Coordinates are btop's 1-based values; see pybtop/ui/pen.py for the cursor model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..collectors.processes import STATE_NAMES
from ..fmt import floating_humanizer
from .pen import (
    DIV_DOWN,
    DIV_LEFT,
    DIV_RIGHT,
    DIV_UP,
    GRAPH_BG,
    H_LINE,
    SUPERSCRIPT,
    TITLE_LEFT,
    TITLE_RIGHT,
    V_LINE,
    Pen,
    c_round,
    cjust,
    create_box,
    graph,
    ljust,
    meter,
    rjust,
    uresize,
)

if TYPE_CHECKING:
    from ..app import App

UP_ARROW = "↑"
DOWN_ARROW = "↓"
ENTER = "↵"
TITLE_LEFT_DOWN = "┘"
TITLE_RIGHT_DOWN = "└"


# ---------- MEM -------------------------------------------------------------------------------


@dataclass
class MemGeo:
    x: int
    y: int
    width: int
    height: int
    mem_w: int
    disks_w: int
    divider: int
    mem_size: int
    mem_meter: int
    graph_h: int
    disk_meter: int


def mem_geometry(app: "App", width: int, height: int, y: int, x: int) -> MemGeo:
    """Mem branch of calcSizes (L2149-2177), default config (swap_disk, mem_graphs, show_disks)."""
    if app.show_disks:
        mem_w = math.ceil((width - 3) / 2)
        mem_w += mem_w % 2
        disks_w = width - mem_w - 2
    else:
        mem_w = width - 1
        disks_w = 0
    divider = x + mem_w
    item_height = 4
    if height - 2 > 2 * item_height:
        mem_size = 3
    elif mem_w > 25:
        mem_size = 2
    else:
        mem_size = 1
    mem_meter = max(0, mem_w - (7 if mem_size > 2 else 17))
    if mem_size == 1:
        mem_meter += 6
    graph_h = max(1, c_round(((height - 1) - (2 if mem_size == 3 else 1) * item_height) / item_height))
    if graph_h > 1:
        mem_meter += 6
    disk_meter = max(-14, width - mem_w - 23)
    if disks_w < 25:
        disk_meter += 14
    return MemGeo(x, y, width, height, mem_w, disks_w, divider, mem_size, mem_meter, graph_h, disk_meter)


def draw_mem(app: "App", pen: Pen, width: int, height: int, y: int, x: int) -> None:
    pal = app.palette
    g = mem_geometry(app, width, height, y, x)
    x = g.x
    box = pal.box("mem")
    create_box(pen, x, y, width, height, box, True, "mem", "", 2,
               rounded=app.cfg.get_bool("rounded_corners"), title_color=pal.title, hi_color=pal.hi_fg, bg=pal.bg)
    title_x = g.divider + 2 if app.show_disks else x + width - 9
    pen.to(y, title_x)
    pen.write("┐", fg=box)
    app.map_mouse("d", y, pen.x, 1, 5)
    pen.write("d", fg=pal.hi_fg, bold=True)
    pen.write("isks", fg=pal.title, bold=False)
    pen.write("┌", fg=box)
    if app.show_disks:
        pen.to(y, x + width - 6)
        pen.write("┐", fg=box)
        app.map_mouse("i", y, pen.x, 1, 2)
        pen.write("io", fg=pal.hi_fg, bold=True)
        pen.write("┌", fg=box)

    pen.to(y, g.divider)
    pen.write(DIV_UP, fg=box)
    pen.to(y + height - 1, g.divider)
    pen.write(DIV_DOWN, fg=pal.div_line)
    for i in range(1, height - 1):
        pen.to(y + i, g.divider)
        pen.write(V_LINE, fg=pal.div_line)

    _mem_stats(app, pen, g)
    if app.show_disks:
        _disks(app, pen, g)


def _mem_stats(app: "App", pen: Pen, g: MemGeo) -> None:
    pal = app.palette
    mem = app.mem
    if mem is None:
        return
    total = max(mem.total, 1)
    pen.to(g.y + 1, g.x + 2)
    pen.write("Total:", fg=pal.title, bold=True)
    pen.write(rjust(floating_humanizer(mem.total), g.mem_w - 9), fg=pal.title, bold=False)
    pen.write("", fg=pal.main_fg)

    stats = [
        ("used", mem.used),
        ("available", mem.available),
        ("cached", mem.cached),
        ("free", mem.free),
    ]
    big_mem = g.mem_w > 21
    cy = 1
    for name, value in stats:
        if cy > g.height - 4:
            break
        title = name.capitalize()
        human = floating_humanizer(value)
        pct = 100.0 * value / total
        if g.mem_size > 2:
            row = g.y + 1 + cy
            if g.graph_h > 0:
                _separator(app, pen, g, row)
            else:
                pen.to(row, g.x + 1)
            pen.write(title[: 10 if big_mem else 5] + ":", fg=pal.title, bold=True)
            pen.to(row, g.x + g.mem_w - 1 - len(human))
            pen.write(human.replace(" ", H_LINE) if g.graph_h > 0 else human, fg=pal.main_fg, bold=False)
            pen.to(g.y + 2 + cy, g.x + (0 if g.graph_h >= 2 else 1))
            _mem_graphic(app, pen, g, name, pct)
            if g.graph_h >= 2:
                pen.l(g.mem_w - 2)
                pen.u(g.graph_h - 1)
            else:
                pen.to(g.y + 2 + cy, g.x + g.mem_w - 5)
            pen.write(rjust(f"{int(round(pct))}%", 4), fg=pal.main_fg)
            cy += 2 if g.graph_h == 0 else g.graph_h + 1
        else:
            pen.to(g.y + 1 + cy, g.x + 2)
            pen.write(ljust(title, 5 if g.mem_size > 1 else 1), fg=pal.title, bold=True)
            if g.graph_h < 2:
                pen.write(" ", fg=pal.main_fg)
            _mem_graphic(app, pen, g, name, pct)
            pen.write(rjust(human, 9 if g.mem_size > 1 else 7), fg=pal.title, bold=False)
            cy += 1 if g.graph_h == 0 else g.graph_h
    if g.graph_h > 0 and cy < g.height - 2:
        _separator(app, pen, g, g.y + 1 + cy)


def _separator(app: "App", pen: Pen, g: MemGeo, row: int) -> None:
    """Horizontal '├───┤' divider across the MEM column (Mem::draw L1218-1219, L1262-1263).

    btop moves to x+2 (the first label column) and steps two cells left onto the box border.
    """
    pal = app.palette
    pen.to(row, g.x + 2)
    pen.l(2)
    pen.write(DIV_LEFT, fg=pal.box("mem"))
    pen.write(H_LINE * (g.mem_w - 1), fg=pal.div_line)
    pen.write(DIV_RIGHT, fg=pal.box("mem") if not app.show_disks else pal.main_fg)
    pen.l(g.mem_w - 1)


def _mem_graphic(app: "App", pen: Pen, g: MemGeo, name: str, pct: float) -> None:
    pal = app.palette
    if app.cfg.get_bool("mem_graphs"):
        hist = list(app.mem_hist.get(name, []))
        graph(pen, hist, g.mem_meter, g.graph_h, pal.gradients[name], no_zero=False)
    else:
        meter(pen, pct, g.mem_meter, pal.gradients[name], pal.meter_bg)


def _disks(app: "App", pen: Pen, g: MemGeo) -> None:
    pal = app.palette
    cx, cy = g.mem_w, 0
    x, y, height = g.x, g.y, g.height
    disks_w = g.disks_w
    big = disks_w >= 25

    def divider(row: int) -> None:
        pen.to(row, x + 1 + cx)
        pen.l(1)
        pen.write(DIV_LEFT, fg=pal.div_line)
        pen.write(H_LINE * disks_w, fg=pal.div_line)
        pen.write(DIV_RIGHT, fg=pal.box("mem"))
        pen.l(disks_w)

    rows = app.disk_rows()
    n = len(rows)
    io_count = sum(1 for disk in rows if "io_activity" in disk)
    show_io = app.cfg.get_bool("show_io_stat")
    for disk in rows:
        if cy > height - 3:
            break
        divider(y + 1 + cy)
        human_total = floating_humanizer(disk["total"], shorten=not big).replace(" ", H_LINE)
        human_used = floating_humanizer(disk["used"], shorten=not big)
        human_io = disk.get("io", "")
        pen.write(uresize(disk["name"], disks_w - 8), fg=pal.title, bold=True)
        pen.to(y + 1 + cy, x + cx + disks_w - len(human_total))
        pen.write(human_total, fg=pal.title, bold=False)
        if big and human_io:
            io_bytes = len(("▼" + human_io).encode("utf-8"))
            pen.to(y + 1 + cy, x + 1 + cx + c_round(disks_w / 2) - c_round(io_bytes / 2) - 1)
            pen.write(H_LINE, fg=pal.div_line)
            pen.write("▼" + human_io, fg=pal.main_fg)
            pen.write(H_LINE, fg=pal.div_line)
        cy += 1
        if cy > height - 3:
            break
        if show_io and "io_activity" in disk:
            pen.to(y + 1 + cy, x + 1 + cx)
            pen.write(" IO% " if big else " IO   ", fg=pal.main_fg)
            if not big:
                pen.l(2)
            pen.write(GRAPH_BG * (disks_w - 6), fg=pal.inactive_fg)
            pen.l(disks_w - 6)
            graph(pen, disk["io_activity"], disks_w - 6, 1, pal.gradients["available"], no_zero=True)
            if not big and human_io:
                pen.to(y + 1 + cy, x + cx + 1)
                pen.write(human_io, fg=pal.main_fg)
            cy += 1
            if cy > height - 3:
                break
        pen.to(y + 1 + cy, x + 1 + cx)
        if big:
            pen.write(" Used:" + rjust(f"{int(round(disk['used_percent']))}%", 4) + " ", fg=pal.main_fg)
        else:
            pen.write("U ", fg=pal.main_fg)
        meter(pen, disk["used_percent"], g.disk_meter, pal.gradients["used"], pal.meter_bg)
        pen.write(rjust(human_used, 9 if big else 5), fg=pal.main_fg)
        cy += 1
        if cy > height - 3:
            break
        if n * 3 + (io_count if show_io else 0) <= height - 1:
            pen.to(y + 1 + cy, x + 1 + cx)
            if big:
                pen.write(" Free:" + rjust(f"{int(round(disk['free_percent']))}%", 4) + " ", fg=pal.main_fg)
            else:
                pen.write("F ", fg=pal.main_fg)
            cy += 1
            if n * 4 + (io_count if show_io else 0) <= height - 1:
                cy += 1
    if cy < height - 2:
        divider(y + 1 + cy)


# ---------- NET -------------------------------------------------------------------------------


def draw_net(app: "App", pen: Pen, width: int, height: int, y: int, x: int) -> None:
    pal = app.palette
    box = pal.box("net")
    b_width = 27 if width > 45 else 19
    b_height = 9 if height > 10 else height - 2
    b_x = x + width - b_width - 1
    b_y = y + ((height - 2) // 2) - b_height // 2 + 1
    d_graph_h = c_round((height - 2) / 2)
    u_graph_h = height - 2 - d_graph_h
    create_box(pen, x, y, width, height, box, True, "net", "", 3,
               rounded=app.cfg.get_bool("rounded_corners"), title_color=pal.title, hi_color=pal.hi_fg, bg=pal.bg)

    iface = app.net_iface or ""
    i_size = min(len(iface), 10)
    pen.to(y, x + width - i_size - 9)
    pen.write("┐", fg=box)
    app.map_mouse("b", y, pen.x, 1, 3)
    pen.write("<b ", fg=pal.hi_fg, bold=True)
    pen.write(uresize(iface, 10), fg=pal.title, bold=False)
    app.map_mouse("n", y, pen.x, 1, 3)
    pen.write(" n>", fg=pal.hi_fg, bold=False)
    pen.write("┌", fg=box)
    pen.to(y, x + width - i_size - 15)
    pen.write("┐", fg=box)
    app.map_mouse("z", y, pen.x, 1, 4)
    pen.write("z", fg=pal.hi_fg, bold=False)
    pen.write("ero", fg=pal.title, bold=False)
    pen.write("┌", fg=box)
    ip = app.net_ip
    if ip and width - i_size - 36 > len(ip):
        pen.to(y, x + 8)
        pen.write("┐", fg=box)
        pen.write(ip, fg=pal.title, bold=True)
        pen.write("┌", fg=box)
    if width - i_size - 20 > 6:
        pen.to(y, x + width - i_size - 21)
        pen.write("┐", fg=box)
        app.map_mouse("a", y, pen.x, 1, 4)
        pen.write("a", fg=pal.hi_fg, bold=app.cfg.get_bool("net_auto"))
        pen.write("uto", fg=pal.title, bold=False)
        pen.write("┌", fg=box)
    if width - i_size - 20 > 13:
        pen.to(y, x + width - i_size - 27)
        pen.write("┐", fg=box)
        app.map_mouse("y", y, pen.x, 1, 4)
        pen.write("s", fg=pal.title, bold=app.cfg.get_bool("net_sync"))
        pen.write("y", fg=pal.hi_fg, bold=False)
        pen.write("nc", fg=pal.title, bold=False)
        pen.write("┌", fg=box)

    down_max = app.net_top_rate("download")
    up_max = app.net_top_rate("upload")
    pen.to(y + 1, x + 1)
    graph(pen, app.net_percent_list("download"), width - b_width - 2, u_graph_h, pal.gradients["download"], no_zero=True)
    pen.to(y + 1 + u_graph_h, x + 1)
    graph(pen, app.net_percent_list("upload"), width - b_width - 2, d_graph_h, pal.gradients["upload"],
          no_zero=True, invert=True)
    pen.to(y + 1, x + 1)
    pen.write(floating_humanizer(down_max, shorten=True), fg=pal.graph_text, bold=False)
    pen.to(y + 1 + height - 3, x + 1)
    pen.write(floating_humanizer(up_max, shorten=True), fg=pal.graph_text, bold=False)

    create_box(pen, b_x, b_y, b_width, b_height, pal.div_line, False, "download", "upload", 0,
               rounded=app.cfg.get_bool("rounded_corners"), title_color=pal.title, bg=pal.bg)

    cy = 0
    for direction, arrow, rate, top, total in (
        ("download", "▼", app.net_down_rate, app.net_top_bytes("download"), app.net_total_rx),
        ("upload", "▲", app.net_up_rate, app.net_top_bytes("upload"), app.net_total_tx),
    ):
        speed = floating_humanizer(rate, per_second=True)
        bits = floating_humanizer(rate, bit=True, per_second=True)
        pen.to(b_y + 1 + cy, b_x + 1)
        pen.write(arrow + " ", fg=pal.main_fg)
        pen.write(ljust(speed, 10), fg=pal.main_fg)
        if b_width >= 20:
            pen.write(rjust("(" + bits + ")", 13), fg=pal.main_fg)
        cy += 2 if b_height == 5 else 1
        if b_height >= 8:
            pen.to(b_y + 1 + cy, b_x + 1)
            top_bits = floating_humanizer(top, bit=True, per_second=True)
            pen.write(arrow + " Top: " + rjust("(" + top_bits, 17 if b_width >= 20 else 9) + ")", fg=pal.main_fg)
            cy += 1
        if b_height >= 6:
            pen.to(b_y + 1 + cy, b_x + 1)
            pen.write(arrow + " Total: " + rjust(floating_humanizer(total), 16 if b_width >= 20 else 8),
                      fg=pal.main_fg)
            cy += 2 if (b_height > 6 and b_height % 2) else 1
        _ = direction


# ---------- PROC ------------------------------------------------------------------------------


DETAIL_ROWS = 8  # rows the detail panel takes at the top of the PROC box (btop's Proc::y + 8)


def draw_proc(app: "App", pen: Pen, width: int, height: int, x: int, y: int) -> None:
    pal = app.palette
    box = pal.box("proc")
    detailed = app.detail is not None
    top = y + DETAIL_ROWS if detailed else y  # list section: its control row, then the column labels
    list_h = height - DETAIL_ROWS if detailed else height
    user_size = 5 if width < 75 else 10
    thread_size = -1 if width < 75 else 4
    prog_size = 16 if width > 70 else (8 if width > 55 else width - user_size - thread_size - 33)
    cmd_size = width - prog_size - user_size - thread_size - 33 if width > 55 else -1
    select_max = list_h - 3
    app.proc_area = (x, y, width, height, top, list_h)
    create_box(pen, x, y, width, height, box, True, "" if detailed else "proc", "", 0 if detailed else 4,
               rounded=app.cfg.get_bool("rounded_corners"), title_color=pal.title, hi_color=pal.hi_fg, bg=pal.bg)
    if detailed:
        _detail_panel(app, pen, x, y, width)
    _list_controls(app, pen, x, top, width)

    pen.to(top + 1, x + 1)
    pen.write(rjust("Pid:", 8) + " ", fg=pal.title, bold=True)
    pen.write(ljust("Program:", prog_size) + " ", fg=pal.title, bold=True)
    if cmd_size > 0:
        pen.write(ljust("Command:", cmd_size) + " ", fg=pal.title, bold=True)
    if app.proc_tree:
        pen.write(ljust("Tree:", 1) + " ", fg=pal.title, bold=True)
    if thread_size > 0:
        pen.l(4)
        pen.write("Threads: ", fg=pal.title, bold=True)
    pen.write(ljust("User:", user_size) + " ", fg=pal.title, bold=True)
    pen.write(rjust("MemB", 5) + " ", fg=pal.title, bold=True)
    pen.write(rjust("Cpu%", 10), fg=pal.title, bold=True)

    visible = app.visible_process_rows(select_max)
    for lc, (proc, depth) in enumerate(visible):
        row = top + 2 + lc
        selected = app.selected_index == app.proc_scroll + lc
        bg = pal.selected_bg if selected else pal.bg
        fg = pal.selected_fg if selected else pal.main_fg
        pen.style(bg=bg)
        pen.to(row, x + 1)
        pen.write(rjust(str(proc.pid), 8) + " ", fg=fg, bold=selected)
        name = proc.prefix + proc.name if app.proc_tree else proc.name
        pen.write(ljust(name, prog_size) + " ", fg=fg, bold=selected)
        if cmd_size > 0:
            pen.write(ljust(proc.command or f"[{proc.name}]", cmd_size), fg=fg, bold=selected)
            pen.to(row, x + 11 + prog_size + cmd_size)
            pen.write(" ", fg=fg)
        if thread_size > 0:
            pen.write(rjust(_threads_text(proc.threads), thread_size) + " ", fg=fg, bold=selected)
        user = proc.user if len(proc.user) <= user_size else proc.user[: user_size - 1] + "+"
        pen.write(ljust(user, user_size) + " ", fg=fg, bold=selected)
        pen.write(rjust(floating_humanizer(proc.rss_bytes, shorten=True), 5) + " ", fg=fg, bold=selected)
        pen.write(GRAPH_BG * 5, fg=pal.inactive_fg)
        pen.l(5)
        hist = list(app.proc_hist.get(proc.pid, []))
        graph(pen, hist, 5, 1, pal.gradients["cpu"], no_zero=True)
        pen.write(" ", fg=fg)
        pen.write(rjust(_cpu_text(proc.cpu_percent), 4) + "  ", fg=fg, bold=selected)
    pen.style(bg=pal.bg)
    if len(app.procs) > select_max:
        _scrollbar(app, pen, x, top, width, list_h, select_max)

    _bottom_controls(app, pen, x, y + height - 1, width)


def _list_controls(app: "App", pen: Pen, x: int, y: int, width: int) -> None:
    """Filter, per-core, reverse, tree and sort buttons on the list's top row (Proc::draw, btop L1659-1693)."""
    pal = app.palette
    box = pal.box("proc")
    pen.to(y, x + 9)
    pen.write("┐", fg=box)
    filter_start = pen.x
    pen.write("f", fg=pal.hi_fg, bold=True)
    if app.filter_text:
        pen.write(f" {app.filter_text}", fg=pal.title, bold=True)
        app.map_mouse("f", y, filter_start, 1, len(app.filter_text) + 2)
        pen.write(" ", fg=pal.hi_fg)
        app.map_mouse("delete", y, pen.x, 1, 3)
        pen.write("del", fg=pal.hi_fg)
    else:
        pen.write("ilter", fg=pal.title, bold=True)
        app.map_mouse("f", y, filter_start, 1, 6)
    pen.write("┌", fg=box)

    sort_len = len(app.proc_sort)
    sort_pos = x + width - sort_len - 8
    if width > 55 + sort_len:
        pen.to(y, sort_pos - 25)
        pen.write("┐", fg=box)
        start = pen.x
        pen.write("per-", fg=pal.title, bold=True)
        pen.write("c", fg=pal.hi_fg, bold=True)
        pen.write("ore", fg=pal.title, bold=True)
        app.map_mouse("c", y, start, 1, 8)
        pen.write("┌", fg=box)
    if width > 45 + sort_len:
        pen.to(y, sort_pos - 15)
        pen.write("┐", fg=box)
        start = pen.x
        pen.write("r", fg=pal.hi_fg, bold=True)
        pen.write("everse", fg=pal.title, bold=True)
        app.map_mouse("r", y, start, 1, 7)
        pen.write("┌", fg=box)
    if width > 35 + sort_len:
        pen.to(y, sort_pos - 6)
        pen.write("┐", fg=box)
        start = pen.x
        pen.write("tre", fg=pal.title, bold=True)
        pen.write("e", fg=pal.hi_fg, bold=True)
        app.map_mouse("e", y, start, 1, 4)
        pen.write("┌", fg=box)
    pen.to(y, sort_pos)
    pen.write("┐", fg=box)
    app.map_mouse("left", y, pen.x, 1, 2)
    pen.write("< ", fg=pal.hi_fg, bold=True)
    pen.write(app.proc_sort, fg=pal.title, bold=True)
    app.map_mouse("right", y, pen.x, 1, 2)
    pen.write(" >", fg=pal.hi_fg, bold=True)
    pen.write("┌", fg=box)


def _bottom_controls(app: "App", pen: Pen, x: int, fy: int, width: int) -> None:
    """Select, info, terminate, kill and signals buttons on the bottom border, plus the position counter."""
    pal = app.palette
    box = pal.box("proc")
    has_procs = bool(app.procs)
    pen.to(fy, x + 1)
    pen.write(TITLE_LEFT_DOWN, fg=box)
    pen.write(UP_ARROW, fg=pal.hi_fg, bold=True)
    pen.write(" select ", fg=pal.title, bold=False)
    pen.write(DOWN_ARROW, fg=pal.hi_fg, bold=True)
    pen.write(TITLE_RIGHT_DOWN, fg=box)
    pen.write(TITLE_LEFT_DOWN, fg=box)
    start = pen.x
    pen.write("info ", fg=pal.title, bold=False)
    pen.write(ENTER, fg=pal.hi_fg, bold=True)
    if has_procs:
        app.map_mouse("enter", fy, start, 1, 6)
    pen.write(TITLE_RIGHT_DOWN, fg=box)
    if width > 60:
        pen.write(TITLE_LEFT_DOWN, fg=box)
        start = pen.x
        pen.write("t", fg=pal.hi_fg, bold=True)
        pen.write("erminate", fg=pal.title, bold=False)
        if has_procs:
            app.map_mouse("t", fy, start, 1, 9)
        pen.write(TITLE_RIGHT_DOWN, fg=box)
    if width > 55:
        pen.write(TITLE_LEFT_DOWN, fg=box)
        start = pen.x
        pen.write("k", fg=pal.hi_fg, bold=True)
        pen.write("ill", fg=pal.title, bold=False)
        if has_procs:
            app.map_mouse("k", fy, start, 1, 4)
        pen.write(TITLE_RIGHT_DOWN, fg=box)
    pen.write(TITLE_LEFT_DOWN, fg=box)
    start = pen.x
    pen.write("s", fg=pal.hi_fg, bold=True)
    pen.write("ignals", fg=pal.title, bold=False)
    if has_procs:
        app.map_mouse("s", fy, start, 1, 7)
    pen.write(TITLE_RIGHT_DOWN, fg=box)

    location = f"{app.selected_index if app.procs else 0}/{len(app.procs)}"
    pen.to(fy, x + width - 3 - max(9, len(location)))
    pen.write(H_LINE * max(0, 9 - len(location)), fg=box)
    pen.write(TITLE_LEFT_DOWN, fg=box)
    pen.write(location, fg=pal.title, bold=True)
    pen.write(TITLE_RIGHT_DOWN, fg=box)


def _detail_panel(app: "App", pen: Pen, x: int, y: int, width: int) -> None:
    """Process detail panel in the top DETAIL_ROWS rows of the PROC box (Proc::draw, show_detailed, L1566-1770).

    Layout: CPU graph on the left, info grid and command on the right, memory line below the grid.
    """
    pal = app.palette
    box = pal.box("proc")
    det = app.detail
    info = det.info
    alive = det.alive
    dgraph_width = max(width // 3, width - 121)
    d_width = width - dgraph_width - 1
    d_x = x + dgraph_width + 1
    top = y + DETAIL_ROWS
    item_fit = max(1, (d_width - 2) // 10)
    item_width = (d_width - 2) // min(item_fit, 8)
    hi_color = pal.hi_fg if alive else pal.inactive_fg
    t_color = pal.title if alive else pal.inactive_fg

    pen.to(top, x)
    pen.write(DIV_LEFT, fg=box)
    pen.write(H_LINE, fg=box)
    pen.write(TITLE_LEFT, fg=box)
    pen.write(SUPERSCRIPT[4], fg=pal.hi_fg, bold=True)
    pen.write("proc", fg=pal.title, bold=True)
    pen.write(TITLE_RIGHT, fg=box)
    pen.write(H_LINE * (width - 10), fg=box)
    pen.write(DIV_RIGHT, fg=box)

    pid_text = str(info.pid)
    pen.to(y, x + 2)
    pen.write(TITLE_LEFT, fg=box)
    pen.write(pid_text, fg=pal.title, bold=True)
    pen.write(TITLE_RIGHT, fg=box)
    pen.write(TITLE_LEFT, fg=box)
    pen.write(uresize(info.name, dgraph_width - len(pid_text) - 7), fg=pal.title, bold=True)
    pen.write(TITLE_RIGHT, fg=box)

    pen.to(y, d_x - 1)
    pen.write(DIV_UP, fg=box)
    pen.to(top, d_x - 1)
    pen.write(DIV_DOWN, fg=pal.div_line)
    for row in range(1, DETAIL_ROWS):
        pen.to(y + row, d_x - 1)
        pen.write(V_LINE, fg=pal.div_line)

    pen.to(y, d_x + 1)
    if width > 55:
        pen.write(TITLE_LEFT, fg=box)
        start = pen.x
        pen.write("t", fg=hi_color, bold=True)
        pen.write("erminate", fg=t_color)
        if alive:
            app.map_mouse("t", y, start, 1, 9)
        pen.write(TITLE_RIGHT, fg=box)
    pen.write(TITLE_LEFT, fg=box)
    start = pen.x
    pen.write("k", fg=hi_color, bold=True)
    pen.write("ill", fg=t_color)
    if alive:
        app.map_mouse("k", y, start, 1, 4)
    pen.write(TITLE_RIGHT, fg=box)
    pen.write(TITLE_LEFT, fg=box)
    start = pen.x
    pen.write("s", fg=hi_color, bold=True)
    pen.write("ignals", fg=t_color)
    if alive:
        app.map_mouse("s", y, start, 1, 7)
    pen.write(TITLE_RIGHT, fg=box)
    pen.to(y, d_x + d_width - 10)
    pen.write(TITLE_LEFT, fg=box)
    start = pen.x
    pen.write("hide ", fg=t_color, bold=True)
    app.map_mouse("enter", y, start, 1, 6)
    pen.write(ENTER, fg=hi_color, bold=True)
    pen.write(TITLE_RIGHT, fg=box)

    status = STATE_NAMES.get(info.state[:1], "Unknown") if alive else "Dead"
    labels = [("Status:", None), ("Elapsed:", None)]
    if item_fit >= 3:
        labels.append(("IO/R:", None))
    if item_fit >= 4:
        labels.append(("IO/W:", None))
    if item_fit >= 5:
        labels.append(("Parent:", None))
    if item_fit >= 6:
        labels.append(("User:", None))
    if item_fit >= 7:
        labels.append(("Threads:", None))
    if item_fit >= 8:
        labels.append(("Nice:", None))
    pen.to(y + 1, d_x + 1)
    pen.write("".join(cjust(label, item_width) for label, _ in labels), fg=pal.title, bold=True)

    io_read = floating_humanizer(det.io[0]) if det.io else ""
    io_write = floating_humanizer(det.io[1]) if det.io else ""
    running = status == "Running" and alive
    stat_color = pal.inactive_fg if not alive else (app.theme.color("proc_misc") if running else pal.main_fg)
    values = [status, det.elapsed, io_read, io_write, det.parent, info.user, str(info.threads), str(info.nice)]
    pen.to(y + 2, d_x + 1)
    pen.write(cjust(values[0], item_width), fg=stat_color)
    pen.write("".join(cjust(value, item_width) for value in values[1 : len(labels)]), fg=pal.main_fg)

    cpu_text = _pct_text(info.cpu_percent) + "%" if alive else ""
    pen.to(y + 1, x + 1)
    graph(pen, list(det.cpu_hist), dgraph_width - 1, DETAIL_ROWS - 1, pal.gradients["cpu"], no_zero=True)
    pen.to(y + 1, x + 1)
    pen.write(cpu_text, fg=pal.title, bold=True)
    for row, label in enumerate("CPU"):
        pen.to(y + 3 + row, x + 1)
        pen.write(label, fg=pal.main_fg)

    total = app.mem.total if app.mem is not None and app.mem.total else 1
    mem_text = ("Memory: " if item_fit > 4 else "M:") + _pct_text(100.0 * info.rss_bytes / total) + "% "
    mem_w = d_width // 3
    pen.to(y + 4, d_x + 1)
    pen.write(rjust(mem_text, mem_w - 2), fg=pal.title, bold=True)
    graph_x = pen.x
    pen.write(GRAPH_BG * mem_w, fg=pal.inactive_fg)
    pen.to(y + 4, graph_x)
    graph(pen, list(det.mem_hist), mem_w, 1, [app.theme.color("proc_misc")], no_zero=False)
    pen.write(" ", fg=pal.main_fg)
    pen.write(floating_humanizer(info.rss_bytes), fg=pal.title, bold=True)

    command = info.command or f"[{info.name}]"
    chunk = d_width - 5
    lines = [command[i * chunk : (i + 1) * chunk] for i in range(min(3, math.ceil(len(command) / chunk)))]
    for row, label in enumerate("CMD"):
        pen.to(y + 5 + row, d_x + 1)
        pen.write(label, fg=pal.main_fg)
    for row, line in enumerate(lines):
        pen.to(y + 5 + (1 if len(lines) == 1 else row), d_x + 3)
        pen.write(cjust(line, chunk), fg=pal.main_fg)


def _pct_text(pct: float) -> str:
    """btop's detail percentage: three characters below 10 or from 100 up, otherwise four."""
    text = f"{pct:f}"
    return text[:3] if pct < 10 or pct >= 100 else text[:4]


def _threads_text(threads: int) -> str:
    return f"{threads // 1000}K" if threads > 9999 else str(threads)


def _cpu_text(pct: float) -> str:
    """Proc::draw cpu string: to_string(double) cut to 3 or 4 characters, 'NNk' for >= 10000."""
    text = f"{pct:f}"
    if pct < 10 or 100 <= pct < 1000:
        return text[:3]
    if pct >= 10000:
        return f"{int(pct // 1000)}k"
    return text[:4]


def _scrollbar(app: "App", pen: Pen, x: int, y: int, width: int, height: int, select_max: int) -> None:
    pal = app.palette
    count = len(app.procs)
    start = app.proc_scroll
    pos = max(0, min(height - 5, c_round(start * select_max / max(1, count - select_max))))
    pen.to(y + 1, x + width - 2)
    pen.write(UP_ARROW, fg=pal.main_fg, bold=True)
    pen.to(y + height - 2, x + width - 2)
    pen.write(DOWN_ARROW, fg=pal.main_fg, bold=False)
    for i in range(y + 2, y + height - 2):
        pen.to(i, x + width - 2)
        pen.write("█" if i == y + 2 + pos else " ", fg=pal.main_fg)
