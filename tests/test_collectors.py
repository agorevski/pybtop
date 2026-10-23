"""Collector parsing and CPU/memory arithmetic against fixed /proc-format samples."""

import re

from pybtop import log
from pybtop.collectors import battery, cpu, memory, processes
from pybtop.config import merge_config_lines, parse_config_text, parse_value
from pybtop.theme import parse_theme_text


PROC_STAT_1 = "cpu  100 0 50 800 50 0 0 0 0 0\ncpu0 50 0 25 400 25 0 0 0 0 0\ncpu1 50 0 25 400 25 0 0 0 0 0\n"
PROC_STAT_2 = "cpu  200 0 100 850 50 0 0 0 0 0\ncpu0 100 0 50 425 25 0 0 0 0 0\ncpu1 100 0 50 425 25 0 0 0 0 0\n"


def test_busy_percent_uses_non_idle_share_of_total_delta():
    before = cpu.parse_proc_stat(PROC_STAT_1).times["cpu"]
    after = cpu.parse_proc_stat(PROC_STAT_2).times["cpu"]
    assert cpu.busy_percent(before, after) == 75.0


def test_busy_percent_is_zero_without_a_previous_sample():
    snap = cpu.parse_proc_stat(PROC_STAT_1).times["cpu"]
    assert cpu.busy_percent(None, snap) == 0.0


def test_core_labels_are_numerically_sorted():
    text = "cpu 1 0 0 1 0 0 0 0 0 0\n" + "".join(f"cpu{i} 1 0 0 1 0 0 0 0 0 0\n" for i in (10, 2, 0))
    assert cpu.core_labels(cpu.parse_proc_stat(text)) == ["cpu0", "cpu2", "cpu10"]


def test_meminfo_used_is_total_minus_available_in_bytes():
    text = (
        "MemTotal:       1000 kB\nMemFree:         100 kB\nMemAvailable:    400 kB\n"
        "Cached:          200 kB\nSReclaimable:     50 kB\nSwapTotal:       100 kB\nSwapFree:         75 kB\n"
    )
    stats = memory.parse_meminfo(text)
    assert stats.used == 600 * 1024
    assert stats.cached == 250 * 1024
    assert stats.swap_used == 25 * 1024


def test_mount_octal_escapes_are_decoded():
    assert memory._unescape_mount_field(r"/mnt/my\040disk") == "/mnt/my disk"


def test_process_stat_handles_spaces_and_parentheses_in_comm():
    # comm is "(sd-pam) x" with a space and parentheses; fields after the last ')' are positional.
    fields = ["S", "1", "0", "0", "0", "0", "0", "0", "0", "0", "0", "7", "3", "0", "0", "20", "0", "4", "0", "99"]
    fields += ["0", "1024"]  # starttime is field 22 (index 19), rss is field 24 (index 21)
    line = "42 ((sd-pam) x) " + " ".join(fields)
    info = processes.parse_stat(42, line)
    assert info is not None
    assert info.name == "(sd-pam) x"
    assert info.state == "S"
    assert info.ppid == 1
    assert (info.utime, info.stime) == (7, 3)
    assert info.threads == 4
    assert info.start_ticks == 99
    assert info.rss_bytes == 1024 * processes.PAGE_SIZE


def test_process_stat_rejects_truncated_input():
    assert processes.parse_stat(1, "1 (init) S 0") is None


def test_process_cmdline_with_escape_sequences_is_read_without_control_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(processes, "PROC", str(tmp_path))
    (tmp_path / "77").mkdir()
    payload = b"sh\0-c\0\x1b]52;c;ZXZpbA==\x07\x1b]0;owned\x07\x1b[2J\x1b[H"
    (tmp_path / "77" / "cmdline").write_bytes(payload)
    command = processes.read_command(77)
    assert "\x1b" not in command and "\x07" not in command
    assert command.startswith("sh -c ")


def test_sort_defaults_are_descending_for_numbers_and_ascending_for_names():
    procs = [
        processes.ProcessInfo(pid=3, ppid=1, name="b", state="S", threads=1, utime=0, stime=0,
                              start_ticks=0, rss_bytes=10, cpu_percent=5.0),
        processes.ProcessInfo(pid=1, ppid=0, name="a", state="S", threads=9, utime=0, stime=0,
                              start_ticks=0, rss_bytes=30, cpu_percent=9.0),
    ]
    assert [p.pid for p in processes.sort_processes(procs, "pid")] == [1, 3]
    assert [p.pid for p in processes.sort_processes(procs, "memory")] == [1, 3]
    assert [p.pid for p in processes.sort_processes(procs, "memory", reverse=True)] == [3, 1]


def _proc(pid: int, cpu: float = 0.0, cumulative: float = 0.0) -> processes.ProcessInfo:
    info = processes.ProcessInfo(pid=pid, ppid=1, name=f"p{pid}", state="S", threads=1, utime=0, stime=0,
                                 start_ticks=0, rss_bytes=0, cpu_percent=cpu)
    info.cpu_cumulative = cumulative
    return info


def test_cpu_lazy_orders_by_lifetime_cpu_while_cpu_direct_uses_current_cpu():
    procs = [_proc(1, cpu=8.0, cumulative=0.1), _proc(2, cpu=0.0, cumulative=0.9)]
    assert [p.pid for p in processes.sort_processes(procs, "cpu lazy")] == [2, 1]
    assert [p.pid for p in processes.sort_processes(procs, "cpu direct")] == [1, 2]


def test_cpu_lazy_pushes_busy_process_above_long_lived_ones():
    idle = [_proc(pid, cumulative=1.0 - pid * 0.01) for pid in range(1, 8)]
    busy = _proc(99, cpu=50.0, cumulative=0.01)
    assert processes.sort_processes(idle + [busy], "cpu lazy")[0].pid == 99


def test_tree_order_nests_children_under_parents():
    base = dict(state="S", threads=1, utime=0, stime=0, start_ticks=0, rss_bytes=0)
    procs = [
        processes.ProcessInfo(pid=1, ppid=0, name="init", **base),
        processes.ProcessInfo(pid=3, ppid=2, name="grandchild", **base),
        processes.ProcessInfo(pid=2, ppid=1, name="child", **base),
    ]
    ordered = [(p.name, depth) for p, depth in processes.tree_order(procs)]
    assert ordered == [("init", 0), ("child", 1), ("grandchild", 2)]


def test_tree_collapse_hides_subtree_and_adds_its_usage_to_the_parent_row():
    base = dict(state="S", threads=1, utime=0, stime=0, start_ticks=0, rss_bytes=0)
    procs = [
        processes.ProcessInfo(pid=1, ppid=0, name="init", cpu_percent=1.0, **base),
        processes.ProcessInfo(pid=2, ppid=1, name="child", cpu_percent=5.0, **base),
        processes.ProcessInfo(pid=3, ppid=2, name="grandchild", cpu_percent=7.0, **base),
    ]
    shown = processes.tree_order(procs, collapsed={2})
    assert [(p.name, depth) for p, depth in shown] == [("init", 0), ("child", 1)]
    child = shown[1][0]
    assert child.cpu_percent == 12.0
    assert child.prefix == " │ [+]─"
    assert procs[1].cpu_percent == 5.0  # the collapsed row is a copy; the sampled process keeps its own value


def test_theme_parser_takes_first_quoted_value_and_ignores_trailing_text():
    text = 'theme[main_bg]="#ff0000" #00ff00"\n# comment\ntheme[title]="#ABC"\n'
    assert parse_theme_text(text) == {"main_bg": "#ff0000", "title": "#ABC"}


def test_config_values_keep_btop_types():
    values = parse_config_text('update_ms = 2000\nproc_tree = True\ncolor_theme = "Default"\nbogus line\n')
    assert values == {"update_ms": 2000, "proc_tree": True, "color_theme": "Default"}
    assert parse_value("False") is False


def test_config_save_keeps_comments_unknown_keys_and_unchanged_lines():
    old = [
        "#? Config file for btop v. 1.3.0",
        "",
        "#* Frame rate.",
        "update_ms = 2000",
        "custom_extra = 7",
        "#* Tree view.",
        "proc_tree = False",
    ]
    values = {"update_ms": 1500, "proc_tree": False, "new_flag": True}
    merged = merge_config_lines(old, values)
    assert merged[:4] == ["#? Config file for btop v. 1.3.0", "", "#* Frame rate.", "update_ms = 1500"]
    assert "custom_extra = 7" in merged and merged[merged.index("proc_tree = False") - 1] == "#* Tree view."
    assert merged.index("new_flag = True") == merged.index("proc_tree = False") + 1


def test_debug_log_uses_btop_line_format(tmp_path):
    path = tmp_path / "btop.log"
    assert log.open_log("0.1.0", "1.3.0", str(path)) == str(path)
    log.debug("Starting in DEBUG mode!")
    log.error("Sampling failed")
    log.close_session()
    lines = path.read_text().splitlines()
    stamp = r"\d{4}/\d{2}/\d{2} \(\d{2}:\d{2}:\d{2}\) \| "
    assert re.fullmatch(stamp + r"===> pybtop 0\.1\.0 \(btop\+\+ 1\.3\.0 compatible\)", lines[0])
    assert re.fullmatch(stamp + r"DEBUG: Starting in DEBUG mode!", lines[1])
    assert re.fullmatch(stamp + r"ERROR: Sampling failed", lines[2])
    assert re.fullmatch(stamp + r"INFO: Quitting! Runtime: 00:00:00", lines[3])
    log.debug("ignored once closed")
    assert len(path.read_text().splitlines()) == 4


def _supply(root, name, **files):
    path = root / name
    path.mkdir()
    for key, value in files.items():
        (path / key).write_text(f"{value}\n")
    return path


def test_battery_percent_and_time_to_empty_come_from_energy_and_power(tmp_path):
    _supply(tmp_path, "BAT0", type="Battery", present=1, status="Discharging",
            energy_now=30000000, energy_full=60000000, power_now=15000000)
    _supply(tmp_path, "AC", type="Mains", present=1, online=1)
    info = battery.read_battery(root=str(tmp_path))
    assert (info.percent, info.status, info.seconds) == (50, "discharging", 7200)


def test_battery_status_falls_back_to_ac_online_and_skips_absent_batteries(tmp_path):
    _supply(tmp_path, "BAT0", type="Battery", present=0, capacity=10, status="Discharging")
    _supply(tmp_path, "BAT1", type="Battery", present=1, capacity=80, status="Unknown")
    _supply(tmp_path, "AC0", type="Mains", present=1, online=1)
    (tmp_path / "BAT1" / "AC0").mkdir()
    (tmp_path / "BAT1" / "AC0" / "online").write_text("1\n")
    info = battery.read_battery(root=str(tmp_path))
    assert (info.percent, info.status, info.seconds) == (80, "charging", -1)


def test_no_battery_or_missing_directory_yields_none(tmp_path):
    _supply(tmp_path, "AC", type="Mains", present=1, online=1)
    assert battery.read_battery(root=str(tmp_path)) is None
    assert battery.read_battery(root=str(tmp_path / "missing")) is None


ARCSTATS_FIXTURE = """13 1 0x01 96 26112 1234 56 0
name                            type data
hits                            4    1000
c_min                           4    1073741824
c                               4    2147483648
size                            4    3221225472
"""


def test_zfs_arc_counts_as_cache_and_as_available_above_c_min():
    meminfo = "MemTotal: 8388608 kB\nMemFree: 1048576 kB\nMemAvailable: 2097152 kB\nCached: 1048576 kB\n"
    plain = memory.parse_meminfo(meminfo)
    with_arc = memory.parse_meminfo(meminfo, memory.parse_arcstats(ARCSTATS_FIXTURE))
    assert with_arc.cached - plain.cached == 3221225472
    assert with_arc.available - plain.available == 3221225472 - 1073741824
    assert memory.parse_arcstats("hits 4 1000\n") is None


def test_zfs_hide_datasets_keeps_pools_and_physical_devices_only():
    mounts = [
        memory.Mount("/dev/sda1", "/", "ext4"),
        memory.Mount("tank", "/tank", "zfs"),
        memory.Mount("tank/home", "/home", "zfs"),
        memory.Mount("nas:/export", "/mnt/nas", "nfs"),
    ]
    shown = [m.mountpoint for m in memory.select_mounts(mounts, only_physical=True)]
    assert shown == ["/", "/tank", "/home"]
    hidden = [m.mountpoint for m in memory.select_mounts(mounts, only_physical=True, zfs_hide_datasets=True)]
    assert hidden == ["/", "/tank"]
