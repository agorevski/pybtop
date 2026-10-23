"""Memory, swap and mounted-disk statistics."""

from __future__ import annotations

import os
from dataclasses import dataclass

PROC_MEMINFO = "/proc/meminfo"
PROC_MOUNTS = "/proc/self/mounts"
ETC_MTAB = "/etc/mtab"
SYS_BLOCK = "/sys/block"
PROC_ARCSTATS = "/proc/spl/kstat/zfs/arcstats"

# Pseudo or virtual filesystems that are never reported as disks.
SKIP_FSTYPES = {
    "autofs", "binfmt_misc", "bpf", "cgroup", "cgroup2", "configfs", "debugfs", "devpts",
    "devtmpfs", "fusectl", "hugetlbfs", "mqueue", "nsfs", "overlay", "proc", "pstore",
    "rpc_pipefs", "securityfs", "selinuxfs", "squashfs", "sysfs", "tmpfs", "tracefs",
}


@dataclass
class MemoryStats:
    total: int
    available: int
    free: int
    cached: int
    swap_total: int
    swap_free: int

    @property
    def used(self) -> int:
        return max(0, self.total - self.available)

    @property
    def used_percent(self) -> float:
        return 100.0 * self.used / self.total if self.total else 0.0

    @property
    def swap_used(self) -> int:
        return max(0, self.swap_total - self.swap_free)

    @property
    def swap_percent(self) -> float:
        return 100.0 * self.swap_used / self.swap_total if self.swap_total else 0.0


def parse_arcstats(text: str) -> tuple[int, int] | None:
    """(ARC size, c_min) in bytes from /proc/spl/kstat/zfs/arcstats, or None when absent."""
    values: dict[str, int] = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] in ("size", "c_min") and fields[2].isdigit():
            values[fields[0]] = int(fields[2])
    if "size" not in values or "c_min" not in values:
        return None
    return values["size"], values["c_min"]


def parse_meminfo(text: str, arcstats: tuple[int, int] | None = None) -> MemoryStats:
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, sep, rest = line.partition(":")
        fields = rest.split()
        if sep and fields:
            values[key] = int(fields[0]) * 1024  # /proc/meminfo reports kB
    free = values.get("MemFree", 0)
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", free)
    cached = values.get("Cached", 0) + values.get("SReclaimable", 0)
    if arcstats is not None:
        # btop counts the ARC as cache, and as available above c_min (the ARC does not shrink below it).
        arc_size, arc_min = arcstats
        cached += arc_size
        if arc_size > arc_min:
            available += arc_size - arc_min
    return MemoryStats(
        total=total,
        available=available,
        free=free,
        cached=cached,
        swap_total=values.get("SwapTotal", 0),
        swap_free=values.get("SwapFree", 0),
    )


def read_memory(path: str = PROC_MEMINFO, arcstats_path: str | None = None) -> MemoryStats:
    arcstats = None
    if arcstats_path is not None:
        try:
            with open(arcstats_path, encoding="ascii") as fh:
                arcstats = parse_arcstats(fh.read())
        except (OSError, UnicodeDecodeError):
            arcstats = None
    with open(path, encoding="ascii") as fh:
        return parse_meminfo(fh.read(), arcstats)


@dataclass
class Mount:
    device: str
    mountpoint: str
    fstype: str


def _unescape_mount_field(text: str) -> str:
    """Decode octal escapes (e.g. \\040 for a space) used by mount tables."""
    out: list[str] = []
    i = 0
    while i < len(text):
        octal = text[i + 1 : i + 4]
        if text[i] == "\\" and len(octal) == 3 and all(c in "01234567" for c in octal):
            out.append(chr(int(octal, 8)))
            i += 4
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def read_mounts() -> list[Mount]:
    """Mounted filesystems from /proc/self/mounts, falling back to /etc/mtab."""
    for path in (PROC_MOUNTS, ETC_MTAB):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        mounts = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 3:
                mounts.append(Mount(parts[0], _unescape_mount_field(parts[1]), parts[2]))
        return mounts
    return []


@dataclass
class DiskUsage:
    name: str
    device: str
    mountpoint: str
    fstype: str
    total: int
    used: int
    free: int

    @property
    def used_percent(self) -> float:
        return 100.0 * self.used / self.total if self.total else 0.0


def disk_usage_for(mount: Mount) -> DiskUsage | None:
    try:
        st = os.statvfs(mount.mountpoint)
    except OSError:
        return None
    return DiskUsage(
        name=mount.mountpoint,
        device=mount.device,
        mountpoint=mount.mountpoint,
        fstype=mount.fstype,
        total=st.f_blocks * st.f_frsize,
        used=(st.f_blocks - st.f_bfree) * st.f_frsize,
        free=st.f_bavail * st.f_frsize,
    )


def select_mounts(mounts: list[Mount], only_physical: bool = True, zfs_hide_datasets: bool = False) -> list[Mount]:
    """Mounts shown in the disks list. ZFS pools (device 'pool') and datasets ('pool/name') are physical;
    zfs_hide_datasets keeps only the pools, as btop does."""
    seen: set[str] = set()
    selected: list[Mount] = []
    for mount in mounts:
        if mount.fstype in SKIP_FSTYPES:
            continue
        if mount.fstype == "zfs" and zfs_hide_datasets and "/" in mount.device:
            continue
        if only_physical and not (mount.device.startswith("/dev/") or mount.fstype == "zfs"):
            continue
        if mount.device in seen:
            continue
        seen.add(mount.device)
        selected.append(mount)
    return selected


def list_disks(only_physical: bool = True, zfs_hide_datasets: bool = False) -> list[DiskUsage]:
    result: list[DiskUsage] = []
    for mount in select_mounts(read_mounts(), only_physical, zfs_hide_datasets):
        usage = disk_usage_for(mount)
        if usage is not None and usage.total > 0:
            result.append(usage)
    return result


@dataclass
class DiskIo:
    read_sectors: int
    write_sectors: int
    io_ticks_ms: int  # time the device spent doing I/O (busy time)


def read_block_io(device: str) -> DiskIo | None:
    """Counters for a partition or disk, e.g. /dev/nvme0n1p2 -> /sys/block/nvme0n1/nvme0n1p2/stat."""
    name = os.path.basename(device)
    paths = [os.path.join(SYS_BLOCK, name, "stat")]
    try:
        paths += [os.path.join(SYS_BLOCK, parent, name, "stat") for parent in os.listdir(SYS_BLOCK)]
    except OSError:
        pass
    for path in paths:
        try:
            with open(path, encoding="ascii") as fh:
                fields = fh.read().split()
            return DiskIo(read_sectors=int(fields[2]), write_sectors=int(fields[6]), io_ticks_ms=int(fields[9]))
        except (OSError, ValueError, IndexError):
            continue
    return None
