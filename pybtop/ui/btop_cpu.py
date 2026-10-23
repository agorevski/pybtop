"""CPU box of btop 1.3.0, ported from Cpu::draw (src/btop_draw.cpp L530-916) and calcSizes L2008-2073.

Default config on a GPU machine: 'cpu' shown, GPUs listed in the CPU panel (show_gpu_info=Auto),
graph_lower resolves to gpu-totals, cpu_invert_lower=true. Coordinates are btop's 1-based values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..fmt import floating_humanizer
from .pen import (
    DIV_LEFT,
    DIV_RIGHT,
    GRAPH_BG,
    H_LINE,
    TITLE_LEFT,
    TITLE_LEFT_DOWN,
    TITLE_RIGHT,
    TITLE_RIGHT_DOWN,
    V_LINE,
    Pen,
    c_round,
    create_box,
    graph,
    meter,
    rjust,
)

if TYPE_CHECKING:
    from ..app import App

UNIT_CELSIUS = "°C"


@dataclass
class CpuGeo:
    x: int
    y: int
    width: int
    height: int
    b_columns: int
    b_column_size: int
    b_width: int
    b_height: int
    b_x: int
    b_y: int
    gpus_extra: int
    mid_line: bool
    graph_up_h: int
    graph_low_h: int
    graph_w: int
    show_temps: bool
    show_gpu: bool


def show_temps(app: "App") -> bool:
    return app.cfg.get_bool("check_temp") and app.cpu_temp is not None


def cpu_geometry(app: "App", width: int, cpu_h: int, y: int) -> CpuGeo:
    """Draw::calcSizes CPU branch: sub-box columns, sizes, and graph heights."""
    cores = len(app.core_pcts)
    gpus = len(app.gpus)
    t = 1 if show_temps(app) else 0
    width_c = width
    gpus_extra = gpus if gpus else 0
    b_columns = max(1, math.ceil((cores + 1) / max(1, cpu_h - gpus_extra - 5)))
    third = width_c // 3
    if b_columns * (21 + 12 * t) < width_c - third:
        size, b_width = 2, (21 + 12 * t) * b_columns - (b_columns - 1)
    elif b_columns * (15 + 6 * t) < width_c - third:
        size, b_width = 1, (15 + 6 * t) * b_columns - (b_columns - 1)
    elif b_columns * (8 + 6 * t) < width_c - third:
        size, b_width = 0, (8 + 6 * t) * b_columns + 1
    else:
        b_columns = max(1, (width_c - third) // (8 + 6 * t))
        size, b_width = 0, (8 + 6 * t) * b_columns + 1
    b_height = min(cpu_h - 2, math.ceil(cores / b_columns) + 4 + gpus_extra)
    x = 1
    b_x = x + width_c - b_width - 1
    b_y = y + math.ceil((cpu_h - 2) / 2) - math.ceil(b_height / 2) + 1

    show_gpu = gpus > 0 and app.cfg.get_str("show_gpu_info") in ("Auto", "On")
    mid_line = show_gpu
    graph_up_h = math.ceil((cpu_h - 2) / 2) - (1 if (mid_line and cpu_h % 2) else 0)
    graph_low_h = cpu_h - 2 - graph_up_h - (1 if mid_line else 0)
    return CpuGeo(
        x=x, y=y, width=width_c, height=cpu_h, b_columns=b_columns, b_column_size=size,
        b_width=b_width, b_height=b_height, b_x=b_x, b_y=b_y, gpus_extra=gpus_extra,
        mid_line=mid_line, graph_up_h=graph_up_h, graph_low_h=graph_low_h,
        graph_w=x + width_c - b_width - 3, show_temps=bool(t), show_gpu=show_gpu,
    )


def draw_cpu(app: "App", pen: Pen, width: int, cpu_h: int, y: int) -> CpuGeo:
    pal = app.palette
    geo = cpu_geometry(app, width, cpu_h, y)
    x, y, w, h = geo.x, geo.y, geo.width, geo.height
    box = pal.box("cpu")
    title, title2 = ("", "cpu") if app.cpu_bottom else ("cpu", "")
    create_box(pen, x, y, w, h, box, True, title, title2, 1,
               rounded=app.cfg.get_bool("rounded_corners"), title_color=pal.title, hi_color=pal.hi_fg, bg=pal.bg)
    _header_buttons(app, pen, geo)
    _draw_battery(app, pen, width)
    _draw_meter_box(app, pen, geo)

    if geo.mid_line:
        pen.to(y + geo.graph_up_h + 1, x)
        pen.write(DIV_LEFT, fg=box)
        pen.write(H_LINE * (w - geo.b_width - 2), fg=pal.div_line)
        pen.write(DIV_RIGHT, fg=box)
        up_name, lo_name = "total", "gpu-totals"
        pen.to(y + geo.graph_up_h + 1, x + ((w - geo.b_width) // 2) - ((len(up_name) + len(lo_name)) // 2) - 4)
        pen.write(up_name, fg=pal.main_fg)
        pen.r(1)
        pen.write("▲▼", fg=pal.main_fg)
        pen.r(1)
        pen.write(lo_name, fg=pal.main_fg)

    pen.to(y + 1, x + 1)
    graph(pen, list(app.cpu_hist), geo.graph_w, geo.graph_up_h, pal.gradients["cpu"], no_zero=True)
    lower_top = y + geo.graph_up_h + 1 + (1 if geo.mid_line else 0)
    pen.to(lower_top, x + 1)
    if geo.show_gpu:
        _draw_gpu_columns(app, pen, geo, lower_top, geo.graph_w, geo.graph_low_h)
    else:
        graph(pen, list(app.cpu_hist), geo.graph_w, geo.graph_low_h, pal.gradients["cpu"],
              no_zero=True, invert=True)

    if app.cfg.get_bool("show_uptime"):
        pen.to(y + h - 2, x + 2)
        pen.write("up", fg=pal.graph_text)
        pen.r(1)
        pen.write(_uptime_string(app), fg=pal.graph_text)

    return geo


def _header_buttons(app: "App", pen: Pen, geo: CpuGeo) -> None:
    pal = app.palette
    x, w = geo.x, geo.width
    y = geo.y + geo.height - 1 if app.cpu_bottom else geo.y
    left, right = (TITLE_LEFT_DOWN, TITLE_RIGHT_DOWN) if app.cpu_bottom else (TITLE_LEFT, TITLE_RIGHT)
    box = pal.box("cpu")
    pen.to(y, x + 10)
    pen.write(left, fg=box)
    app.map_mouse("m", y, pen.x, 1, 4)
    pen.write("m", fg=pal.hi_fg, bold=True)
    pen.write("enu", fg=pal.title, bold=False)
    pen.write(right, fg=box)
    pen.to(y, x + 16)
    pen.write(left, fg=box)
    app.map_mouse("p", y, pen.x, 1, 8)
    pen.write("p", fg=pal.hi_fg, bold=True)
    pen.write("reset ", fg=pal.title, bold=False)
    pen.write(app.preset_label, fg=pal.title)
    pen.write(right, fg=box)
    update = f"{app.update_ms}ms"
    pen.to(y, x + w - len(update) - 8)
    pen.write(left, fg=box)
    app.map_mouse("-", y, pen.x, 1, 2)
    pen.write("- ", fg=pal.hi_fg, bold=True)
    pen.write(update, fg=pal.title)
    app.map_mouse("+", y, pen.x, 1, 2)
    pen.write(" +", fg=pal.hi_fg)
    pen.write(right, fg=box)
    pen.to(y, x + w // 2 - 4)
    pen.write(left, fg=box)
    pen.write(app.clock_text, fg=pal.title, bold=True)
    pen.write(right, fg=box)


BATTERY_SYMBOLS = {"charging": "▲", "discharging": "▼", "full": "■", "unknown": "○"}


def _draw_battery(app: "App", pen: Pen, width: int) -> None:
    """Battery title on the CPU box's top border (Cpu::draw, btop_draw.cpp L705-744), right of the clock."""
    bat = app.battery
    if bat is None:
        return
    pal = app.palette
    time_text = ""
    if bat.seconds > 0:
        hours, minutes = divmod(bat.seconds // 60, 60)
        time_text = f"{hours:02d}:{minutes:02d}"
    wide = width >= 100
    pct_text = f"{bat.percent}%"
    cur_len = (11 if wide else 0) + len(time_text) + len(pct_text) + len(str(app.update_ms))
    pen.to(1, width - cur_len - 17)
    box = pal.box("cpu")
    pen.write(DIV_RIGHT, fg=box)
    pen.write("BAT" + BATTERY_SYMBOLS.get(bat.status, BATTERY_SYMBOLS["unknown"]) + " " + pct_text,
              fg=pal.title, bold=True)
    if wide:
        pen.write(" ", fg=pal.title, bold=False)
        meter(pen, bat.percent, 10, pal.gradients["cpu"], pal.meter_bg, invert=True)
    pen.write(" " + time_text, fg=pal.title, bold=True)
    pen.write(DIV_LEFT, fg=box, bold=False)


def _uptime_string(app: "App") -> str:
    text = app.uptime_text
    return text[:-3] if len(text) > 8 else text


def _column_widths(width: int, n: int) -> tuple[int, int]:
    """Per-GPU column widths (L604, L625): (width of columns 0..n-2, width of the last column)."""
    d = width
    w = d // n - n + 1 + d % n
    w_last = w + d % w - n + 1 if w > 0 else 0
    return w, w_last


def _draw_gpu_columns(app: "App", pen: Pen, geo: CpuGeo, top: int, area_w: int, area_h: int) -> None:
    """Per-GPU graph columns with 'GPU i' labels and vertical dividers (draw_graphs, L748-778)."""
    pal = app.palette
    n = len(app.gpus)
    if area_h <= 0 or area_w <= 0:
        return
    w, w_last = _column_widths(area_w, n)
    left = geo.x + 1
    hist_list = list(app.gpu_hist)
    for i in range(n):
        col_w = w if i < n - 1 else w_last
        pen.to(top, left)
        values = list(hist_list[i]) if i < len(hist_list) else []
        graph(pen, values, col_w, area_h, pal.gradients["cpu"], no_zero=True, invert=True)
        if n > 1:
            label = str(i)
            prefix = "GPU " if w > 5 else ""
            pen.l(w - 1)
            pen.u(area_h // 2)
            pen.write(prefix + label, fg=pal.main_fg)
            pen.d(area_h // 2)
            pen.r(w - 1 - (4 if w > 5 else 0) - len(label))
        if i + 1 < n:
            pen.write("", fg=pal.div_line)
            for _ in range(area_h):
                pen.write(V_LINE, fg=pal.div_line)
                pen.l(1)
                pen.u(1)
            pen.r(1)
            pen.d(1)
        left += col_w + 1


def _draw_meter_box(app: "App", pen: Pen, geo: CpuGeo) -> None:
    pal = app.palette
    b_x, b_y, b_w, b_h = geo.b_x, geo.b_y, geo.b_width, geo.b_height
    size, cols = geo.b_column_size, geo.b_columns
    t = geo.show_temps
    rounded = app.cfg.get_bool("rounded_corners")
    title = _cpu_name(app, b_w)
    create_box(pen, b_x, b_y, b_w, b_h, pal.div_line, False, title, "", 0, rounded=rounded,
               title_color=pal.title, bg=pal.bg)

    if app.cfg.get_bool("show_cpu_freq") and app.freqs:
        hz = f"{max(app.freqs) / 1000:.1f} GHz"
        pen.to(b_y, b_x + b_w - 10)
        pen.write(H_LINE * max(0, 7 - len(hz)), fg=pal.div_line)
        pen.write("┐", fg=pal.div_line)
        pen.write(hz, fg=pal.title, bold=True)
        pen.write("┌", fg=pal.div_line)

    total = int(round(app.cpu_pct))
    pen.to(b_y + 1, b_x + 1)
    pen.write("CPU ", fg=pal.main_fg, bold=True)
    meter_w = b_w - (23 - (6 if size <= 1 and cols == 1 else 0) if t else 11)
    meter(pen, total, meter_w, pal.gradients["cpu"], pal.meter_bg)
    pen.write(rjust(str(total), 4), fg=pal.gradient_color("cpu", total))
    pen.write("%", fg=pal.main_fg)
    if t:
        temp = int(round(app.cpu_temp))
        if size > 1 or cols > 1:
            pen.write(" ", fg=pal.inactive_fg)
            pen.write(GRAPH_BG * 5, fg=pal.inactive_fg)
            pen.l(5)
            graph(pen, list(app.cpu_temp_hist), 5, 1, pal.gradients["temp"], no_zero=False)
        pen.write(rjust(str(temp), 4), fg=pal.main_fg)
        pen.write(UNIT_CELSIUS, fg=pal.main_fg)
    pen.write(V_LINE, fg=pal.div_line)

    cx, cy, cc = 0, 1, 0
    show_temps_flag = geo.show_temps and app.cfg.get_bool("show_coretemp")
    core_w = 2 if size == 0 else 3
    if len(app.core_pcts) >= 100:
        core_w += 1
    core_graphs_built = size > 0
    cores = len(app.core_pcts)
    per_col = math.ceil(cores / cols) if cols else cores
    for n in range(cores):
        if not core_graphs_built:
            break  # btop builds its per-core graph objects only when size > 0 (L687), so L814 ends the loop
        pen.to(b_y + cy + 1, b_x + cx + 1)
        pen.write("C", fg=pal.main_fg, bold=True)
        pen.write(f"{n:<{core_w}}"[:core_w], fg=pal.main_fg, bold=False)
        pen.write(GRAPH_BG * (5 * size), fg=pal.inactive_fg)
        pen.l(5 * size)
        hist = list(app.core_hist[n]) if n < len(app.core_hist) else []
        graph(pen, hist, 5 * size, 1, pal.gradients["cpu"], no_zero=True)
        pct = int(round(app.core_pcts[n]))
        pen.write(rjust(str(pct), 3 if size < 2 else 4), fg=pal.gradient_color("cpu", pct))
        pen.write("%", fg=pal.main_fg)
        temp_slots = (cores + 1) if size > 1 else 1
        core_temp = app.core_temp(n) if show_temps_flag and n <= temp_slots else None
        if core_temp is not None:
            if size > 1:
                pen.write(" ", fg=pal.inactive_fg)
                pen.write(GRAPH_BG * 5, fg=pal.inactive_fg)
                pen.l(5)
                graph(pen, [], 5, 1, pal.gradients["temp"], no_zero=False)
            pen.write(rjust(str(int(round(core_temp))), 4), fg=pal.main_fg)
            pen.write(UNIT_CELSIUS, fg=pal.main_fg)
        pen.write(V_LINE, fg=pal.div_line)
        cy += 1
        if (cy > per_col or cy == b_h - 2) and n != cores - 1:
            cc += 1
            if cc >= cols:
                break
            cy = 1
            cx = (b_w // cols) * cc

    if cy < b_h - 1 and cc <= cols:
        pre, sep = _load_prefix(size, t)
        a, b, c = app.loadavg
        if pre == "L":
            vals = [str(c_round(v)) for v in (a, b, c)]
        else:
            vals = [f"{v:f}"[:4] for v in (a, b, c)]
        lav = pre + "".join(" " * sep + v for v in vals)
        row = b_h - 2 - (len(app.gpus) if geo.show_gpu else 0)
        pen.to(b_y + row, b_x + cx + 1)
        pen.write(lav, fg=pal.main_fg)

    if geo.show_gpu:
        _draw_gpu_brief_rows(app, pen, geo)


def _load_prefix(size: int, t: bool) -> tuple[str, int]:
    if size == 2 and t:
        return "Load AVG:", 3
    if size == 2 or (size == 1 and t):
        return "LAV:", 1
    if size == 1 or (size == 0 and t):
        return "L", 1
    return "", 1


def _cpu_name(app: "App", b_w: int) -> str:
    name = app.cpu_model or "CPU"
    limit = b_w - (14 if app.cfg.get_bool("show_cpu_freq") and app.freqs else 4)
    return name[: max(0, limit)]


def _draw_gpu_brief_rows(app: "App", pen: Pen, geo: CpuGeo) -> None:
    """GPU brief rows inside the CPU sub-box (L876-911). btop's loop breaks after its first pass."""
    pal = app.palette
    b_x, b_y, b_w, b_h = geo.b_x, geo.b_y, geo.b_width, geo.b_height
    gpus = app.gpus
    g = len(gpus)
    cy = b_h - 2 - g
    for i, gpu in enumerate(gpus):
        cy += 1
        pen.to(b_y + cy, b_x + 1)
        pen.write("GPU", fg=pal.main_fg, bold=True)
        if geo.show_temps and gpu.temp_c is not None and b_w < 34:
            if gpu.temp_c < 100:
                pen.write(" ", fg=pal.main_fg)
        if g > 1:
            pen.write(rjust(str(i), 1 + (1 if g > 9 else 0)), fg=pal.main_fg)
        util = gpu.util_percent or 0.0
        mem_total_txt = floating_humanizer(gpu.mem_total or 0, True) if gpu.mem_total else ""
        gpu_meter_w = (
            b_w - 12 - len(mem_total_txt) - (24 if geo.show_temps else 12) - len(str(i))
            + (2 if g == 1 else 0) - (1 if g > 9 and i <= 9 else 0)
        )
        if gpu.util_percent is not None:
            if gpu_meter_w > 1:
                pen.write(" ", fg=pal.main_fg)
            meter(pen, util, gpu_meter_w, pal.gradients["cpu"], pal.meter_bg)
            pen.write(rjust(str(int(round(util))), 4), fg=pal.gradient_color("cpu", util))
            pen.write("%", fg=pal.main_fg)
        else:
            pen.r(max(0, gpu_meter_w))
        if gpu.mem_used is not None:
            pen.write(" ", fg=pal.main_fg)
            pen.write(GRAPH_BG * 6, fg=pal.inactive_fg)
            pen.l(6)
            mem_pct = 100.0 * gpu.mem_used / gpu.mem_total if gpu.mem_total else 0.0
            graph(pen, [mem_pct], 5, 1, pal.gradients["used"], no_zero=True)
            pen.write(rjust(floating_humanizer(gpu.mem_used, True), 5), fg=pal.main_fg)
            if gpu.mem_total is not None:
                pen.write("/", fg=pal.inactive_fg)
                pen.write(floating_humanizer(gpu.mem_total, True), fg=pal.main_fg)
            else:
                pen.r(5)
        else:
            pen.r(17)
        if geo.show_temps and gpu.temp_c is not None:
            temp = int(round(gpu.temp_c))
            if b_w > 38:
                pen.write(" ", fg=pal.main_fg)
                pen.write(GRAPH_BG * 6, fg=pal.inactive_fg)
                pen.l(6)
                temp_hist = list(app.gpu_temp_hist[i]) if i < len(app.gpu_temp_hist) else []
                graph(pen, temp_hist, 5, 1, pal.gradients["temp"], no_zero=False)
            pen.write(rjust(str(temp), 3 + (1 if (b_w >= 34 or temp > 99) else 0)), fg=pal.main_fg)
            pen.write(UNIT_CELSIUS, fg=pal.main_fg)
        if cy < b_h - 1:
            break
