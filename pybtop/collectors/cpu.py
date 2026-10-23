"""CPU usage, frequency, load average and uptime from /proc and /sys."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

PROC_STAT = "/proc/stat"
PROC_UPTIME = "/proc/uptime"
PROC_CPUINFO = "/proc/cpuinfo"
CPUFREQ_DIR = "/sys/devices/system/cpu/cpufreq"
LOADAVG = "/proc/loadavg"


@dataclass
class CpuTimes:
    idle: int  # idle + iowait
    total: int


@dataclass
class CpuSnapshot:
    """Cumulative jiffy counters keyed by label ("cpu" for aggregate, "cpu0".. per core)."""

    times: dict[str, CpuTimes] = field(default_factory=dict)


def parse_proc_stat(text: str) -> CpuSnapshot:
    snap = CpuSnapshot()
    for line in text.splitlines():
        if not line.startswith("cpu"):
            continue
        parts = line.split()
        vals = [int(x) for x in parts[1:9]]
        vals += [0] * (8 - len(vals))
        user, nice, system, idle, iowait, irq, softirq, steal = vals
        idle_all = idle + iowait
        non_idle = user + nice + system + irq + softirq + steal
        snap.times[parts[0]] = CpuTimes(idle=idle_all, total=idle_all + non_idle)
    return snap


def read_proc_stat(path: str = PROC_STAT) -> CpuSnapshot:
    with open(path, encoding="ascii", errors="replace") as fh:
        return parse_proc_stat(fh.read())


def busy_percent(prev: CpuTimes | None, cur: CpuTimes) -> float:
    """Percent of non-idle time between two samples, clamped to 0..100."""
    if prev is None:
        return 0.0
    total_delta = cur.total - prev.total
    if total_delta <= 0:
        return 0.0
    idle_delta = cur.idle - prev.idle
    pct = 100.0 * (total_delta - idle_delta) / total_delta
    return max(0.0, min(100.0, pct))


def core_labels(snap: CpuSnapshot) -> list[str]:
    return sorted(
        (k for k in snap.times if re.fullmatch(r"cpu\d+", k)),
        key=lambda s: int(s[3:]),
    )


def read_uptime_seconds(path: str = PROC_UPTIME) -> float:
    with open(path, encoding="ascii") as fh:
        return float(fh.read().split()[0])


def format_uptime(seconds: float) -> str:
    """Uptime as 'D days H:MM:SS' style text (see the CPU box uptime label)."""
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    clock = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{days}d {clock}" if days else clock


def read_loadavg(path: str = LOADAVG) -> tuple[float, float, float]:
    with open(path, encoding="ascii") as fh:
        a, b, c = fh.read().split()[:3]
    return float(a), float(b), float(c)


def cpu_model_name(path: str = PROC_CPUINFO) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def read_frequencies_mhz() -> list[float]:
    """Current frequency per cpufreq policy; falls back to /proc/cpuinfo MHz values."""
    freqs: list[float] = []
    try:
        policies = sorted(p for p in os.listdir(CPUFREQ_DIR) if p.startswith("policy"))
    except OSError:
        policies = []
    for name in policies:
        try:
            with open(os.path.join(CPUFREQ_DIR, name, "scaling_cur_freq"), encoding="ascii") as fh:
                freqs.append(int(fh.read().strip()) / 1000.0)
        except (OSError, ValueError):
            continue
    if freqs:
        return freqs
    try:
        with open(PROC_CPUINFO, encoding="ascii", errors="replace") as fh:
            for line in fh:
                if line.startswith("cpu MHz"):
                    freqs.append(float(line.split(":", 1)[1]))
    except (OSError, ValueError):
        pass
    return freqs


def btop_cpu_name(model: str) -> str:
    """btop's Cpu::get_cpuName (src/linux/btop_collect.cpp:319-383), Xeon/Duo branch and cleanup.

    For a Xeon model, btop takes the word after 'CPU' (so '... CPU @ 3.00GHz' yields '@') and does no
    further cleanup. Other models are cleaned of vendor and marketing words.
    """
    words = model.split()
    name = model
    if ("Xeon" in model or "Duo" in words) and "CPU" in words:
        pos = words.index("CPU")
        name = words[pos + 1] if pos < len(words) - 1 and not words[pos + 1].endswith(")") else ""
    if not name:
        name = model
        for word in ("Processor", "CPU", "(R)", "(TM)", "Intel", "AMD", "Core"):
            name = name.replace(word, "")
        name = " ".join(name.split())
    return name
