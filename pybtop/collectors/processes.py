"""Per-process data from /proc/<pid>/{stat,cmdline} and owner lookup."""

from __future__ import annotations

import os
import pwd
import time
from dataclasses import dataclass, field, replace

PROC = "/proc"
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100

# Process state letters as btop 1.3.0 expands them in its detail panel.
STATE_NAMES = {
    "R": "Running", "S": "Sleeping", "D": "Waiting", "Z": "Zombie", "T": "Stopped", "t": "Tracing",
    "X": "Dead", "x": "Dead", "K": "Wakekill", "W": "Unknown", "P": "Parked",
}


@dataclass
class ProcessInfo:
    pid: int
    ppid: int
    name: str  # comm, as shown by the kernel
    state: str
    threads: int
    utime: int  # clock ticks
    stime: int
    start_ticks: int
    rss_bytes: int
    nice: int = 0
    uid: int = -1
    command: str = ""
    user: str = ""
    kernel_thread: bool = False
    # Derived per refresh:
    cpu_percent: float = 0.0
    mem_percent: float = 0.0
    children: list[int] = field(default_factory=list)
    prefix: str = ""  # tree-view prefix, set by tree_order

    @property
    def cpu_ticks(self) -> int:
        return self.utime + self.stime


def parse_stat(pid: int, text: str) -> ProcessInfo | None:
    """Parse /proc/<pid>/stat. The comm field may contain spaces and parentheses, so split on the last ')'."""
    open_paren = text.find("(")
    close_paren = text.rfind(")")
    if open_paren < 0 or close_paren < 0 or close_paren < open_paren:
        return None
    name = text[open_paren + 1 : close_paren]
    rest = text[close_paren + 2 :].split()
    if len(rest) < 22:
        return None
    # rest[0] is field 3 (state); field N lives at rest[N - 3].
    try:
        return ProcessInfo(
            pid=pid,
            ppid=int(rest[1]),
            name=name,
            state=rest[0],
            utime=int(rest[11]),
            stime=int(rest[12]),
            threads=int(rest[17]),
            nice=int(rest[16]),
            start_ticks=int(rest[19]),
            rss_bytes=int(rest[21]) * PAGE_SIZE,
        )
    except ValueError:
        return None


def read_command(pid: int) -> str:
    try:
        with open(os.path.join(PROC, str(pid), "cmdline"), "rb") as fh:
            raw = fh.read()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()


def read_io(pid: int) -> tuple[int, int] | None:
    """Bytes read and written from /proc/<pid>/io, or None when the file is not readable."""
    values: dict[str, int] = {}
    try:
        with open(os.path.join(PROC, str(pid), "io"), encoding="ascii", errors="replace") as fh:
            for line in fh:
                key, _, value = line.partition(":")
                if key in ("read_bytes", "write_bytes"):
                    values[key] = int(value)
    except (OSError, ValueError):
        return None
    if len(values) < 2:
        return None
    return values["read_bytes"], values["write_bytes"]


def user_name(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except (KeyError, OverflowError):
        return str(uid)


def list_pids() -> list[int]:
    try:
        return [int(p) for p in os.listdir(PROC) if p.isdigit()]
    except OSError:
        return []


def read_process(pid: int) -> ProcessInfo | None:
    base = os.path.join(PROC, str(pid))
    try:
        with open(os.path.join(base, "stat"), encoding="utf-8", errors="replace") as fh:
            info = parse_stat(pid, fh.read())
        owner_uid = os.stat(base).st_uid
    except OSError:
        return None
    if info is None:
        return None
    info.uid = owner_uid
    info.user = user_name(owner_uid)
    info.command = read_command(pid)
    # Kernel threads have an empty cmdline and a zero RSS in the common case.
    info.kernel_thread = info.command == "" and info.rss_bytes == 0
    return info


class ProcessSampler:
    """Builds the process table and turns tick deltas into per-process CPU and memory percentages."""

    def __init__(self, total_memory: int) -> None:
        self.total_memory = total_memory
        self._prev_ticks: dict[int, int] = {}
        self._prev_time: float | None = None

    def sample(self, per_core: bool = False, now: float | None = None) -> list[ProcessInfo]:
        now = time.monotonic() if now is None else now
        elapsed = (now - self._prev_time) if self._prev_time is not None else 0.0
        procs: list[ProcessInfo] = []
        for pid in list_pids():
            info = read_process(pid)
            if info is not None:
                procs.append(info)
        cores = os.cpu_count() or 1
        ticks_now: dict[int, int] = {}
        for info in procs:
            ticks_now[info.pid] = info.cpu_ticks
            prev = self._prev_ticks.get(info.pid)
            if prev is not None and elapsed > 0:
                pct = 100.0 * (info.cpu_ticks - prev) / (elapsed * CLK_TCK)
                info.cpu_percent = max(0.0, pct if per_core else pct / cores)
            info.mem_percent = 100.0 * info.rss_bytes / self.total_memory if self.total_memory else 0.0
        self._prev_ticks = ticks_now
        self._prev_time = now
        return procs


SORT_KEYS = ("pid", "program", "arguments", "threads", "user", "memory", "cpu lazy", "cpu direct")


_SORT_KEY_FUNCS = {
    "pid": (lambda p: p.pid, False),
    "program": (lambda p: p.name.lower(), False),
    "arguments": (lambda p: (p.command or p.name).lower(), False),
    "threads": (lambda p: p.threads, True),
    "user": (lambda p: p.user.lower(), False),
    "memory": (lambda p: p.rss_bytes, True),
    "cpu lazy": (lambda p: p.cpu_percent, True),
    "cpu direct": (lambda p: p.cpu_percent, True),
}


def sort_processes(procs: list[ProcessInfo], key: str, reverse: bool = False) -> list[ProcessInfo]:
    """Order processes by a sort key. Numeric keys default to descending; text and pid to ascending."""
    func, descending = _SORT_KEY_FUNCS.get(key, _SORT_KEY_FUNCS["cpu lazy"])
    return sorted(procs, key=func, reverse=descending != reverse)


def filter_processes(procs: list[ProcessInfo], text: str, hide_kernel: bool = False) -> list[ProcessInfo]:
    needle = text.lower()
    out = []
    for proc in procs:
        if hide_kernel and proc.kernel_thread:
            continue
        if needle and needle not in proc.name.lower() and needle not in proc.command.lower():
            continue
        out.append(proc)
    return out


def tree_order(
    procs: list[ProcessInfo], collapsed: set[int] | frozenset[int] = frozenset()
) -> list[tuple[ProcessInfo, int]]:
    """Depth-first ordering by parent pid. Returns (process, depth) pairs and sets each prefix.

    As in btop, a pid in `collapsed` hides its subtree and its row shows the summed CPU, memory and
    threads of that subtree; collapsed and parent rows carry a '[+]─' or '[-]─' marker.
    """
    by_pid = {p.pid: p for p in procs}
    children: dict[int, list[ProcessInfo]] = {}
    roots: list[ProcessInfo] = []
    for proc in procs:
        if proc.ppid in by_pid and proc.ppid != proc.pid:
            children.setdefault(proc.ppid, []).append(proc)
        else:
            roots.append(proc)
    ordered: list[tuple[ProcessInfo, int]] = []
    seen: set[int] = set()

    def walk(proc: ProcessInfo, depth: int, last: bool) -> None:
        if proc.pid in seen:
            return
        seen.add(proc.pid)
        kids = sorted(children.get(proc.pid, []), key=lambda c: c.pid)
        shown = proc
        if kids and proc.pid in collapsed:
            shown = _with_subtree_totals(proc, children)
        if kids:
            marker = "[+]─" if proc.pid in collapsed else "[-]─"
        else:
            marker = " └─ " if last else " ├─ "
        shown.prefix = " │ " * depth + marker
        ordered.append((shown, depth))
        if proc.pid in collapsed:
            return
        for index, child in enumerate(kids):
            walk(child, depth + 1, index == len(kids) - 1)

    for root in sorted(roots, key=lambda p: p.pid):
        walk(root, 0, False)
    return ordered


def _with_subtree_totals(proc: ProcessInfo, children: dict[int, list[ProcessInfo]]) -> ProcessInfo:
    """Copy of `proc` whose CPU, memory and thread counts include every descendant (the originals stay intact)."""
    descendants: list[ProcessInfo] = []
    stack = list(children.get(proc.pid, []))
    while stack:
        child = stack.pop()
        descendants.append(child)
        stack.extend(children.get(child.pid, []))
    return replace(
        proc,
        cpu_percent=proc.cpu_percent + sum(c.cpu_percent for c in descendants),
        rss_bytes=proc.rss_bytes + sum(c.rss_bytes for c in descendants),
        threads=proc.threads + sum(c.threads for c in descendants),
    )
