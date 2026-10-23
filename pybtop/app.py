"""Application state, sampling loop, input handling and terminal management."""

from __future__ import annotations

import os
import select
import signal
import sys
import termios
import time
import tty
from collections import deque
from dataclasses import dataclass, field
from . import config as config_mod
from . import log
from .collectors import cpu as cpu_c
from .collectors import memory as mem_c
from .collectors import network as net_c
from .collectors import processes as proc_c
from .collectors import sensors as sens_c
from .defaults import DEFAULTS
from .fmt import floating_humanizer
from .keys import KeyDecoder
from .presets import Preset, PresetError, parse_preset_string, select_preset
from .render.ansi import Canvas
from .theme import Theme, available_themes, load_theme, tty_theme
from .ui import layout
from .ui import overlays as ov
from .ui import btop_boxes, btop_cpu
from .ui.palette import Palette
from .ui.pen import Pen

VERSION = "0.1.0"
BTOP_COMPAT_VERSION = "1.3.0"
ALL_BOXES = ["cpu", "mem", "net", "proc"]
SORT_CYCLE = ["pid", "program", "arguments", "threads", "user", "memory", "cpu direct", "cpu lazy"]
HISTORY = 360
NET_TOP_FLOOR = 10 * 1024
MIN_UPDATE_MS, MAX_UPDATE_MS = 100, 86400000
SIGNAL_NAMES = {"terminate": signal.SIGTERM, "kill": signal.SIGKILL}


@dataclass
class CliOptions:
    low_color: bool = False
    tty: bool | None = None
    preset: int | None = None
    update_ms: int | None = None
    utf_force: bool = False
    debug: bool = False


@dataclass
class PresetOverride:
    boxes: set[str]
    cpu_bottom: bool
    proc_left: bool
    mem_below_net: bool
    symbols: dict[str, str] = field(default_factory=dict)


class App:
    def __init__(self, cfg: config_mod.Config, cli: CliOptions, user_theme_dir: str) -> None:
        self.cfg = cfg
        self.cli = cli
        self.user_theme_dir = user_theme_dir
        self.running = True
        self.dirty = True
        self.status = ""
        self.status_until = 0.0

        self.tty_mode = cli.tty if cli.tty is not None else cfg.get_bool("force_tty")
        self.low_color = cli.low_color or not cfg.get_bool("truecolor") or self.tty_mode
        self.update_ms = cli.update_ms if cli.update_ms is not None else cfg.get_int("update_ms")
        self.show_disks = cfg.get_bool("show_disks")
        self.io_mode = cfg.get_bool("io_mode")
        self.clock_text = ""

        self._load_theme()

        self.presets: list[Preset] = []
        try:
            self.presets = parse_preset_string(cfg.get_str("presets"))
        except PresetError:
            self.presets = parse_preset_string(str(DEFAULTS["presets"]))
        self.preset_label = "*"
        self.preset_state: int | None = None  # None = '*' (no preset); 0 = all boxes; n = preset n
        self.preset_override: PresetOverride | None = None
        self.shown: set[str] = set(cfg.get_str("shown_boxes").split()) & set(ALL_BOXES + [f"gpu{i}" for i in range(6)])
        self.cpu_bottom = cfg.get_bool("cpu_bottom")
        self.proc_left = cfg.get_bool("proc_left")
        self.mem_below_net = cfg.get_bool("mem_below_net")
        if cli.preset is not None:
            self.apply_preset(cli.preset)

        # Sampling state.
        self.cpu_prev: cpu_c.CpuSnapshot | None = None
        self.cpu_pct = 0.0
        self.core_pcts: list[float] = []
        self.cpu_hist: deque[float] = deque(maxlen=HISTORY)
        self.cpu_temp_hist: deque[float] = deque(maxlen=HISTORY)
        self.gpu_temp_hist: list[deque[float]] = []
        self.cpu_model = cpu_c.btop_cpu_name(cpu_c.cpu_model_name())
        self.core_ids = sens_c.read_core_ids()
        self.core_hist: list[deque[float]] = []
        self.cpu_temp: float | None = None
        self.core_temps: dict[int, float] = {}
        self.freqs: list[float] = []
        self.uptime_text = ""
        self.loadavg = (0.0, 0.0, 0.0)
        self.mem: mem_c.MemoryStats | None = None
        self.mem_hist: dict[str, deque[float]] = {k: deque(maxlen=HISTORY) for k in ("used", "available", "cached", "free")}
        self.disks: list[mem_c.DiskUsage] = []
        self._io_prev: dict[str, tuple[float, mem_c.DiskIo]] = {}
        self._disk_rate: dict[str, float] = {}
        self.disk_io_hist: dict[str, deque[float]] = {}
        self.net_monitor = net_c.NetMonitor(cfg.get_str("net_iface"))
        self.net_iface: str | None = None
        self.net_ip = ""
        self.net_rate: net_c.NetRate | None = None
        self.net_down_raw: deque[float] = deque(maxlen=HISTORY)
        self.net_up_raw: deque[float] = deque(maxlen=HISTORY)
        self.net_total_rx = 0
        self.net_total_tx = 0
        self.net_scale_top = NET_TOP_FLOOR
        self.gpu_reader = sens_c.NvidiaGpus()
        self.gpus: list[sens_c.GpuInfo] = []
        self.gpu_hist: list[deque[float]] = []
        self.proc_sampler = proc_c.ProcessSampler(self.mem.total if self.mem else 0)
        self.procs: list[proc_c.ProcessInfo] = []
        self._all_procs: list[proc_c.ProcessInfo] = []
        self.proc_depths: dict[int, int] = {}
        self.proc_hist: dict[int, deque[float]] = {}
        self.proc_sort = cfg.get_str("proc_sorting")
        self.proc_reversed = cfg.get_bool("proc_reversed")
        self.proc_tree = cfg.get_bool("proc_tree")
        self.selected_index = 0
        self.selected_pid: int | None = None
        self.proc_scroll = 0
        self.filter_text = ""
        self.filter_buffer = ""
        self.filter_editing = False

        # Overlays and prompts.
        self.overlay: str | None = None
        self.help_page = 0
        self.options_sel = 0
        self.menu_sel = 0
        self.confirm: tuple[str, int, str] | None = None
        self.signal_buf: str | None = None
        self.values_snapshot = dict(cfg.values)
        self.proc_page_rows = 10

        self.sample()

    # ----- configuration helpers -------------------------------------------------------------

    def _load_theme(self) -> None:
        name = self.cfg.get_str("color_theme")
        self.theme: Theme = load_theme(name, self.user_theme_dir)
        self._build_palette()

    def _build_palette(self) -> None:
        # btop uses its TTY theme whenever tty mode is on, whatever color_theme says.
        theme = tty_theme() if self.tty_mode else self.theme
        self.palette = Palette.from_theme(theme, self.cfg.get_bool("theme_background"))

    def visible_gpus(self) -> list[sens_c.GpuInfo]:
        if self.cfg.get_str("show_gpu_info") == "Off":
            return []
        return self.gpus

    def symbol_for(self, box: str) -> str:
        if self.tty_mode:
            return "tty"
        if self.preset_override and box in self.preset_override.symbols:
            symbol = self.preset_override.symbols[box]
            if symbol != "default":
                return symbol
        per_box = self.cfg.get_str(f"graph_symbol_{box}") if box in ("cpu", "gpu", "mem", "net", "proc") else "default"
        if per_box and per_box != "default":
            return per_box
        return self.cfg.get_str("graph_symbol")

    def apply_preset(self, index: int) -> None:
        """index 0 = all boxes with default settings; 1..n = configured preset entries."""
        self.preset_state = index
        if index == 0:
            self.preset_override = None
            self.preset_label = "0"
            self.shown = set(ALL_BOXES)
            self.cpu_bottom = self.cfg.get_bool("cpu_bottom")
            self.proc_left = False
            self.mem_below_net = False
            return
        preset = select_preset(self.presets, index)
        if preset is None:
            return
        self.preset_label = str(min(index, len(self.presets)))
        self.shown = set(preset.boxes)
        position = {e.box: e.position for e in preset.entries}
        self.cpu_bottom = position.get("cpu", 0) == 1
        self.proc_left = position.get("proc", 0) == 1
        self.mem_below_net = position.get("mem", 0) == 1
        self.preset_override = PresetOverride(
            boxes=set(preset.boxes),
            cpu_bottom=self.cpu_bottom,
            proc_left=self.proc_left,
            mem_below_net=self.mem_below_net,
            symbols={e.box: e.symbol for e in preset.entries},
        )

    def cycle_preset(self, step: int) -> None:
        count = len(self.presets)
        if count == 0:
            return
        states = list(range(0, count + 1))  # 0 = all boxes, then each preset
        if self.preset_state is None:
            nxt = states[0] if step > 0 else states[-1]
        else:
            nxt = states[(states.index(self.preset_state) + step) % len(states)]
        self.apply_preset(nxt)

    # ----- sampling --------------------------------------------------------------------------

    def sample(self) -> None:
        now = time.monotonic()
        snap = cpu_c.read_proc_stat()
        labels = cpu_c.core_labels(snap)
        self.core_pcts = []
        if self.cpu_prev is not None:
            self.cpu_pct = cpu_c.busy_percent(self.cpu_prev.times.get("cpu"), snap.times["cpu"])
            self.core_pcts = [
                cpu_c.busy_percent(self.cpu_prev.times.get(label), snap.times[label]) for label in labels
            ]
        else:
            self.core_pcts = [0.0 for _ in labels]
        self.cpu_prev = snap
        if len(self.core_hist) != len(labels):
            self.core_hist = [deque(maxlen=HISTORY) for _ in labels]
        self.cpu_hist.append(self.cpu_pct)
        for hist, pct in zip(self.core_hist, self.core_pcts):
            hist.append(pct)

        self.freqs = cpu_c.read_frequencies_mhz()
        self.uptime_text = cpu_c.format_uptime(cpu_c.read_uptime_seconds())
        self.loadavg = cpu_c.read_loadavg()
        clock_format = self.cfg.get_str("clock_format")
        self.clock_text = time.strftime(clock_format) if clock_format else ""

        chips = sens_c.read_hwmon_chips() if self.cfg.get_bool("check_temp") else []
        self.cpu_temp = sens_c.cpu_package_temp(chips)
        self.core_temps = sens_c.core_temps(chips)
        self.cpu_temp_hist.append(self.cpu_temp or 0.0)

        self.mem = mem_c.read_memory()
        total = self.mem.total or 1
        self.mem_hist["used"].append(100.0 * self.mem.used / total)
        self.mem_hist["available"].append(100.0 * self.mem.available / total)
        self.mem_hist["cached"].append(100.0 * self.mem.cached / total)
        self.mem_hist["free"].append(100.0 * self.mem.free / total)
        self.disks = mem_c.list_disks(self.cfg.get_bool("only_physical"))
        self._sample_disk_io(now)

        rate = self.net_monitor.sample(now)
        self.net_iface = self.net_monitor.iface
        self.net_ip = net_c.interface_ipv4(self.net_iface or "")
        self.net_rate = rate
        self.net_down_raw.append(rate.download if rate else 0.0)
        self.net_up_raw.append(rate.upload if rate else 0.0)
        self.net_total_rx = self.net_monitor.total_rx
        self.net_total_tx = self.net_monitor.total_tx

        self.gpus = self.gpu_reader.read()
        if len(self.gpu_hist) != len(self.gpus):
            self.gpu_hist = [deque(maxlen=HISTORY) for _ in self.gpus]
            self.gpu_temp_hist = [deque(maxlen=HISTORY) for _ in self.gpus]
        for hist, gpu in zip(self.gpu_hist, self.gpus):
            hist.append(gpu.util_percent or 0.0)
        for hist, gpu in zip(self.gpu_temp_hist, self.gpus):
            hist.append(gpu.temp_c or 0.0)

        self.proc_sampler.total_memory = self.mem.total
        all_procs = self.proc_sampler.sample(per_core=self.cfg.get_bool("proc_per_core"), now=now)
        self._all_procs = all_procs
        for proc in all_procs:
            hist = self.proc_hist.setdefault(proc.pid, deque(maxlen=10))
            hist.append(proc.cpu_percent)
        live = {p.pid for p in all_procs}
        for pid in [pid for pid in self.proc_hist if pid not in live]:
            del self.proc_hist[pid]
        self._rebuild_process_list(all_procs)
        self.dirty = True

    def _rebuild_process_list(self, all_procs: list[proc_c.ProcessInfo]) -> None:
        procs = all_procs
        if self.cfg.get_bool("proc_filter_kernel"):
            procs = [p for p in procs if not p.kernel_thread]
        if self.filter_text:
            procs = proc_c.filter_processes(procs, self.filter_text, hide_kernel=False)
        self.proc_depths = {}
        if self.proc_tree:
            ordered = proc_c.tree_order(procs)
            if self.proc_reversed:
                ordered = list(reversed(ordered))
            self.procs = [p for p, _ in ordered]
            self.proc_depths = {p.pid: depth for p, depth in ordered}
        else:
            self.procs = proc_c.sort_processes(procs, self.proc_sort, reverse=self.proc_reversed)
        self.selected_index = max(0, min(self.selected_index, len(self.procs) - 1))
        self.selected_pid = self.procs[self.selected_index].pid if self.procs else None

    def visible_process_rows(self, rows: int) -> list[tuple[proc_c.ProcessInfo, int]]:
        if rows <= 0:
            return []
        if self.selected_index < self.proc_scroll:
            self.proc_scroll = self.selected_index
        elif self.selected_index >= self.proc_scroll + rows:
            self.proc_scroll = self.selected_index - rows + 1
        self.proc_scroll = max(0, min(self.proc_scroll, max(0, len(self.procs) - rows)))
        window = self.procs[self.proc_scroll : self.proc_scroll + rows]
        return [(p, self.proc_depths.get(p.pid, 0)) for p in window]

    # ----- network scaling ------------------------------------------------------------------

    def net_top_rate(self, direction: str) -> float:
        """Top of the graph scale in bytes per second for 'download' or 'upload'."""
        if self.cfg.get_bool("net_auto"):
            if self.cfg.get_bool("net_sync"):
                peak = max(max(self.net_down_raw, default=0.0), max(self.net_up_raw, default=0.0))
            else:
                raw = self.net_down_raw if direction == "download" else self.net_up_raw
                peak = max(raw, default=0.0)
            top = NET_TOP_FLOOR
            while top < peak:
                top *= 10
            return top
        mbit = self.cfg.get_int("net_download" if direction == "download" else "net_upload")
        return max(1, mbit) * 131072.0

    def net_percent_list(self, direction: str) -> list[float]:
        """Recent speeds as a percentage of the graph scale (0..100), oldest first."""
        top = self.net_top_rate(direction)
        raw = self.net_down_raw if direction == "download" else self.net_up_raw
        return [min(100.0, 100.0 * v / top) for v in raw]

    def core_temp(self, cpu_id: int) -> float | None:
        """Temperature of the physical core that logical processor `cpu_id` belongs to."""
        core_id = self.core_ids.get(cpu_id)
        return self.core_temps.get(core_id) if core_id is not None else None

    def net_top_bytes(self, direction: str) -> float:
        """Highest observed speed in bytes per second for the session window."""
        raw = self.net_down_raw if direction == "download" else self.net_up_raw
        return max(raw, default=0.0)

    @property
    def net_down_rate(self) -> float:
        return self.net_rate.download if self.net_rate else 0.0

    @property
    def net_up_rate(self) -> float:
        return self.net_rate.upload if self.net_rate else 0.0

    def _sample_disk_io(self, now: float) -> None:
        """Per-mount busy percent (io_ticks delta) and throughput (sector delta), as btop's IO% row shows."""
        for disk in self.disks:
            io = mem_c.read_block_io(disk.device)
            if io is None:
                continue
            prev = self._io_prev.get(disk.mountpoint)
            hist = self.disk_io_hist.setdefault(disk.mountpoint, deque(maxlen=HISTORY))
            rate = 0.0
            if prev is not None and now > prev[0]:
                dt = now - prev[0]
                busy = (io.io_ticks_ms - prev[1].io_ticks_ms) / (dt * 1000.0) * 100.0
                sectors = (io.read_sectors - prev[1].read_sectors) + (io.write_sectors - prev[1].write_sectors)
                rate = max(0, sectors) * 512 / dt
                hist.append(max(0.0, min(100.0, busy)))
            self._io_prev[disk.mountpoint] = (now, io)
            self._disk_rate[disk.mountpoint] = rate

    def disk_rows(self) -> list[dict]:
        """Disks in btop's display order (mounts, then swap as a disk row)."""
        rows: list[dict] = []
        for disk in self.disks:
            name = "root" if disk.mountpoint == "/" else os.path.basename(disk.mountpoint.rstrip("/")) or disk.mountpoint
            row = {
                "name": name, "total": disk.total, "used": disk.used, "free": disk.free,
                "used_percent": disk.used_percent,
                "free_percent": 100.0 * disk.free / disk.total if disk.total else 0.0,
            }
            if disk.mountpoint in self.disk_io_hist:
                rate = self._disk_rate.get(disk.mountpoint, 0.0)
                row["io"] = floating_humanizer(rate, shorten=True) if rate > 0 else ""
                row["io_activity"] = list(self.disk_io_hist[disk.mountpoint])
            rows.append(row)
        mem = self.mem
        if mem is not None and mem.swap_total and self.cfg.get_bool("show_swap") and self.cfg.get_bool("swap_disk"):
            rows.insert(min(1, len(rows)), {
                "name": "swap", "total": mem.swap_total, "used": mem.swap_used, "free": mem.swap_free,
                "used_percent": mem.swap_percent,
                "free_percent": 100.0 * mem.swap_free / mem.swap_total,
            })
        return rows

    # ----- input -----------------------------------------------------------------------------

    def handle_key(self, key: str) -> None:
        self.dirty = True
        if self.signal_buf is not None:
            return self._key_signal_prompt(key)
        if self.confirm is not None:
            return self._key_confirm(key)
        if self.filter_editing:
            return self._key_filter(key)
        if key == "ctrl+c" or (key == "q" and self.overlay is None):
            self.running = False
            return
        if self.overlay == "help":
            return self._key_help(key)
        if self.overlay == "options":
            return self._key_options(key)
        if self.overlay == "menu":
            return self._key_menu(key)
        self._key_main(key)

    def _key_main(self, key: str) -> None:
        if key in ("esc", "m"):
            self.overlay, self.menu_sel = "menu", 0
        elif key in ("h", "?", "f1"):
            self.overlay, self.help_page = "help", 0
        elif key in ("o", "f2"):
            self.overlay, self.options_sel = "options", 0
        elif key in ("1", "2", "3", "4"):
            self._toggle_box(["cpu", "mem", "net", "proc"][int(key) - 1])
        elif key == "5":
            self.cfg["show_gpu_info"] = "Off" if self.cfg.get_str("show_gpu_info") != "Off" else "Auto"
        elif key == "d":
            self.show_disks = not self.show_disks
            self.cfg["show_disks"] = self.show_disks
        elif key == "i":
            self.io_mode = not self.io_mode
            self.cfg["io_mode"] = self.io_mode
        elif key == "p":
            self.cycle_preset(1)
        elif key == "P":
            self.cycle_preset(-1)
        elif key in ("+", "-"):
            step = 100 if key == "+" else -100
            self.update_ms = max(MIN_UPDATE_MS, min(MAX_UPDATE_MS, self.update_ms + step))
            self.cfg["update_ms"] = self.update_ms
        elif key == "up":
            self._move_selection(-1)
        elif key == "down":
            self._move_selection(1)
        elif key == "pgup":
            self._move_selection(-self._page())
        elif key == "pgdn":
            self._move_selection(self._page())
        elif key == "home":
            self._set_selection(0)
        elif key == "end":
            self._set_selection(len(self.procs) - 1)
        elif key == "left":
            self._cycle_sort(-1)
        elif key == "right":
            self._cycle_sort(1)
        elif key == "r":
            self.proc_reversed = not self.proc_reversed
            self.cfg["proc_reversed"] = self.proc_reversed
            self._rebuild_process_list(self.procs)
        elif key == "e":
            self.proc_tree = not self.proc_tree
            self.cfg["proc_tree"] = self.proc_tree
            self._rebuild_process_list(self.procs)
        elif key == "c":
            self.cfg["proc_per_core"] = not self.cfg.get_bool("proc_per_core")
        elif key == "%":
            self.cfg["proc_mem_bytes"] = not self.cfg.get_bool("proc_mem_bytes")
        elif key in ("f", "/"):
            self.filter_editing, self.filter_buffer = True, self.filter_text
        elif key == "delete":
            self.filter_text = ""
        elif key in ("b", "n"):
            self._cycle_interface(-1 if key == "b" else 1)
        elif key == "a":
            self.cfg["net_auto"] = not self.cfg.get_bool("net_auto")
        elif key == "y":
            self.cfg["net_sync"] = not self.cfg.get_bool("net_sync")
        elif key == "z":
            self.net_monitor.total_rx = 0
            self.net_monitor.total_tx = 0
        elif key in ("t", "enter"):
            self._request_confirm("terminate")
        elif key == "k":
            self._request_confirm("kill")
        elif key == "s":
            self.signal_buf = ""

    def _key_help(self, key: str) -> None:
        if key in ("esc", "q", "h", "?", "f1"):
            self.overlay = None
        elif key == "down":
            self.help_page = min(self.help_page + 1, len(ov.HELP_PAGES) - 1)
        elif key == "up":
            self.help_page = max(self.help_page - 1, 0)

    def _key_options(self, key: str) -> None:
        count = len(ov.OPTIONS)
        if key in ("esc", "o", "f2", "q"):
            self.overlay = None
        elif key == "up":
            self.options_sel = (self.options_sel - 1) % count
        elif key == "down":
            self.options_sel = (self.options_sel + 1) % count
        elif key in ("left", "right", "enter", "space"):
            self._change_option(self.options_sel, -1 if key == "left" else 1)

    def _change_option(self, index: int, step: int) -> None:
        label, key, kind, choices, _ = ov.OPTIONS[index]
        current = self.cfg[key]
        if kind == "bool":
            self.cfg[key] = not current
        elif kind == "theme":
            names = available_themes(self.user_theme_dir)
            pos = names.index(current) if current in names else 0
            self.cfg[key] = names[(pos + step) % len(names)]
            self._load_theme()
        elif kind == "choice":
            pos = choices.index(current) if current in choices else 0
            self.cfg[key] = choices[(pos + step) % len(choices)]
        elif kind == "int":
            self.cfg[key] = max(MIN_UPDATE_MS, min(MAX_UPDATE_MS, current + step * 100))
            self.update_ms = self.cfg[key]
        self._refresh_settings()

    def _refresh_settings(self) -> None:
        """Recompute values derived from config: colour depth, tty mode and palette."""
        self.tty_mode = self.cli.tty if self.cli.tty is not None else self.cfg.get_bool("force_tty")
        self.low_color = self.cli.low_color or not self.cfg.get_bool("truecolor") or self.tty_mode
        self._build_palette()

    def _key_menu(self, key: str) -> None:
        items = ov.MENU_ITEMS
        if key in ("esc", "m", "q"):
            self.overlay = None
        elif key == "up":
            self.menu_sel = (self.menu_sel - 1) % len(items)
        elif key == "down":
            self.menu_sel = (self.menu_sel + 1) % len(items)
        elif key == "enter":
            choice = items[self.menu_sel]
            if choice == "Options":
                self.overlay, self.options_sel = "options", 0
            elif choice == "Help":
                self.overlay, self.help_page = "help", 0
            else:
                self.running = False

    def _key_filter(self, key: str) -> None:
        if key == "enter":
            self.filter_text = self.filter_buffer
            self.filter_editing = False
        elif key == "esc":
            self.filter_editing = False
        elif key == "backspace":
            self.filter_buffer = self.filter_buffer[:-1]
        elif len(key) == 1 and key.isprintable():
            self.filter_buffer += key
        self._rebuild_process_list(self._all_procs)

    def _key_confirm(self, key: str) -> None:
        action, pid, name = self.confirm  # type: ignore[misc]
        self.confirm = None
        if key != "y":
            return
        if action.startswith("signal:"):
            sig = int(action.split(":", 1)[1])
            self._send_signal(pid, name, sig, f"signal {sig}")
        else:
            self._send_signal(pid, name, SIGNAL_NAMES[action], action)

    def _key_signal_prompt(self, key: str) -> None:
        if key == "esc":
            self.signal_buf = None
        elif key == "enter":
            buf, self.signal_buf = self.signal_buf or "", None
            proc = self._selected_proc()
            if not (buf.isdigit() and 1 <= int(buf) <= 64):
                self._flash("Invalid signal number")
            elif proc is not None:
                self.confirm = (f"signal:{int(buf)}", proc.pid, proc.name)
        elif key == "backspace":
            self.signal_buf = (self.signal_buf or "")[:-1]
        elif key.isdigit() and len(key) == 1:
            self.signal_buf = (self.signal_buf or "") + key

    def _request_confirm(self, action: str) -> None:
        proc = self._selected_proc()
        if proc is not None:
            self.confirm = (action, proc.pid, proc.name)

    def _selected_proc(self) -> proc_c.ProcessInfo | None:
        return self.procs[self.selected_index] if self.procs else None

    def _send_signal(self, pid: int, name: str, sig: int, label: str) -> None:
        try:
            os.kill(pid, sig)
            self._flash(f"Sent {label} to {name} ({pid})")
        except ProcessLookupError:
            self._flash(f"No such process {pid}")
        except PermissionError:
            self._flash(f"Permission denied sending to {pid}")

    def _flash(self, message: str) -> None:
        self.status = message
        self.status_until = time.monotonic() + 3.0

    def _toggle_box(self, box: str) -> None:
        if box in self.shown:
            self.shown.discard(box)
        else:
            self.shown.add(box)
        self.cfg["shown_boxes"] = " ".join(b for b in ALL_BOXES if b in self.shown)

    def _cycle_interface(self, step: int) -> None:
        names = net_c.list_interfaces()
        if not names:
            return
        current = self.net_iface if self.net_iface in names else names[0]
        nxt = names[(names.index(current) + step) % len(names)]
        self.net_monitor.preferred = nxt
        self.cfg["net_iface"] = nxt
        self.net_monitor.iface = None

    def _cycle_sort(self, step: int) -> None:
        current = self.proc_sort if self.proc_sort in SORT_CYCLE else "cpu lazy"
        nxt = SORT_CYCLE[(SORT_CYCLE.index(current) + step) % len(SORT_CYCLE)]
        self.proc_sort = nxt
        self.cfg["proc_sorting"] = nxt
        self._rebuild_process_list(self.procs)

    def _move_selection(self, delta: int) -> None:
        self._set_selection(self.selected_index + delta)

    def _set_selection(self, index: int) -> None:
        if not self.procs:
            return
        self.selected_index = max(0, min(index, len(self.procs) - 1))
        self.selected_pid = self.procs[self.selected_index].pid

    def _page(self) -> int:
        return max(1, self.proc_page_rows)

    # ----- rendering -------------------------------------------------------------------------

    def render(self, width: int, height: int) -> str:
        canvas = Canvas(width, height)
        pal = self.palette
        if pal.bg is not None:
            canvas.fill_rect(0, 0, height, width, pal.bg)
        if not layout.fits(width, height):
            ov.draw_too_small(canvas, pal, width, height, layout.MIN_WIDTH, layout.MIN_HEIGHT)
            return canvas.render(self.low_color)

        rects = layout.compute(width, height, len(self.gpus))
        visible = {"cpu": "cpu", "mem": "mem", "net": "net", "proc": "proc"}
        rects = {name: rect for name, rect in rects.items() if name in self.shown and name in visible}
        if not rects:
            ov.draw_prompt(canvas, pal, "No boxes shown!", [
                "1 | Show CPU box", "2 | Show MEM box", "3 | Show NET box", "4 | Show PROC box",
                "5-0 | Show GPU boxes", "esc | Show menu", "q | Quit",
            ])
            return canvas.render(self.low_color)

        self.proc_page_rows = max(1, rects["proc"].inner.height - 1) if "proc" in rects else 10
        pen = Pen(canvas)
        if "cpu" in rects:
            btop_cpu.draw_cpu(self, pen, width, rects["cpu"].height)
        if "mem" in rects:
            mem = rects["mem"]
            btop_boxes.draw_mem(self, pen, mem.width, mem.height, mem.row + 1)
        if "net" in rects:
            net = rects["net"]
            btop_boxes.draw_net(self, pen, net.width, net.height, net.row + 1)
        if "proc" in rects:
            proc = rects["proc"]
            btop_boxes.draw_proc(self, pen, proc.width, proc.height, proc.col + 1, proc.row + 1)

        if self.overlay == "help":
            ov.draw_help(canvas, pal, self.help_page)
        elif self.overlay == "options":
            values = {key: self.cfg[key] for _, key, _, _, _ in ov.OPTIONS}
            ov.draw_options(canvas, pal, self.options_sel, values)
        elif self.overlay == "menu":
            ov.draw_menu(canvas, pal, self.menu_sel, ov.MENU_ITEMS)
        if self.confirm is not None:
            action, pid, name = self.confirm
            verb = action.replace("signal:", "send signal ") if action.startswith("signal:") else action
            ov.draw_prompt(canvas, pal, "Confirm", [
                f"{verb.capitalize()} to {name} (pid {pid})?  y = yes, any other key = no",
            ])
        if self.signal_buf is not None:
            ov.draw_prompt(canvas, pal, "Send signal", [f"Signal number: {self.signal_buf}_", "enter send  esc cancel"])
        if self.status and time.monotonic() < self.status_until:
            canvas.put(height - 1, 0, self.status[: width], fg=self.palette.title, bold=True)
        return canvas.render(self.low_color)

    # ----- persistence -----------------------------------------------------------------------

    def save_config(self, path: str) -> None:
        self.cfg["shown_boxes"] = " ".join(b for b in ALL_BOXES if b in self.shown)
        self.cfg["proc_sorting"] = self.proc_sort
        if self.cfg.values != self.values_snapshot:
            log.debug(f"Writing new config file: {path}")
            config_mod.write_config(self.cfg.values, path)


def run(app: App, config_path: str) -> int:
    """Enter the alternate screen, run the sampling/input loop, then restore the terminal."""
    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    out = sys.stdout
    decoder = KeyDecoder()
    tty.setcbreak(fd)
    out.write("\x1b[?1049h\x1b[?25l\x1b[2J")
    out.flush()
    last_size: tuple[int, int] | None = None
    next_tick = time.monotonic() + app.update_ms / 1000.0
    try:
        while app.running:
            now = time.monotonic()
            timeout = max(0.0, min(next_tick - now, 0.25))
            ready, _, _ = select.select([fd], [], [], timeout)
            if ready:
                keys = decoder.feed(os.read(fd, 1024))
                for key in keys:
                    app.handle_key(key)
                    if not app.running:
                        break
            else:
                for key in decoder.flush():
                    app.handle_key(key)
            if time.monotonic() >= next_tick:
                started = time.perf_counter()
                try:
                    app.sample()
                except Exception as exc:
                    log.error(f"Sampling failed: {exc!r}")
                    raise
                log.debug(f"Collect took {(time.perf_counter() - started) * 1e6:.0f} us")
                next_tick = time.monotonic() + app.update_ms / 1000.0
            size = os.get_terminal_size(fd)
            if size != last_size or app.dirty:
                last_size = size
                app.dirty = False
                out.write(app.render(size.columns, size.lines))
                out.flush()
            if app.status and time.monotonic() >= app.status_until:
                app.status = ""
                app.dirty = True
    finally:
        out.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        out.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        app.gpu_reader.close()
        try:
            app.save_config(config_path)
        except OSError as exc:
            log.error(f"Could not save config to {config_path}: {exc}")
            sys.stderr.write(f"Warning: could not save config to {config_path}: {exc}\n")
        log.close_session()
    return 0


__all__ = ["App", "CliOptions", "run", "VERSION"]
