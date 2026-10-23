"""Network interface selection and throughput counters."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

SYS_NET = "/sys/class/net"
PROC_NET_ROUTE = "/proc/net/route"


def default_interface(route_path: str = PROC_NET_ROUTE) -> str | None:
    """Interface carrying the default route (destination 00000000), if any."""
    try:
        with open(route_path, encoding="ascii") as fh:
            next(fh, None)  # header
            for line in fh:
                fields = line.split()
                if len(fields) >= 2 and fields[1] == "00000000":
                    return fields[0]
    except OSError:
        pass
    return None


def list_interfaces() -> list[str]:
    try:
        return sorted(os.listdir(SYS_NET))
    except OSError:
        return []


def pick_interface(preferred: str = "") -> str | None:
    """Explicit net_iface wins; otherwise the default-route interface, then the first non-loopback."""
    names = list_interfaces()
    if preferred and preferred in names:
        return preferred
    default = default_interface()
    if default and default in names:
        return default
    for name in names:
        if name != "lo":
            return name
    return None


def read_counters(iface: str) -> tuple[int, int] | None:
    """Cumulative (rx_bytes, tx_bytes) for an interface, or None if unreadable."""
    base = os.path.join(SYS_NET, iface, "statistics")
    try:
        with open(os.path.join(base, "rx_bytes"), encoding="ascii") as fh:
            rx = int(fh.read())
        with open(os.path.join(base, "tx_bytes"), encoding="ascii") as fh:
            tx = int(fh.read())
    except (OSError, ValueError):
        return None
    return rx, tx


@dataclass
class NetRate:
    """Bytes per second for one sampling interval."""

    download: float
    upload: float


class NetMonitor:
    """Tracks one interface and converts cumulative counters into per-second rates."""

    def __init__(self, preferred: str = "") -> None:
        self.preferred = preferred
        self.iface: str | None = None
        self._last: tuple[int, int] | None = None
        self._last_time: float | None = None
        self.total_rx = 0
        self.total_tx = 0

    def sample(self, now: float | None = None) -> NetRate | None:
        now = time.monotonic() if now is None else now
        iface = pick_interface(self.preferred)
        if iface != self.iface:
            self.iface = iface
            self._last = None
            self._last_time = None
        if iface is None:
            return None
        counters = read_counters(iface)
        if counters is None:
            return None
        rate = None
        if self._last is not None and self._last_time is not None:
            dt = now - self._last_time
            d_rx = counters[0] - self._last[0]
            d_tx = counters[1] - self._last[1]
            if dt > 0 and d_rx >= 0 and d_tx >= 0:
                rate = NetRate(download=d_rx / dt, upload=d_tx / dt)
                self.total_rx += d_rx
                self.total_tx += d_tx
        self._last = counters
        self._last_time = now
        return rate


SIOCGIFADDR = 0x8915


def interface_ipv4(iface: str) -> str:
    """Primary IPv4 address of an interface, or '' when it has none (SIOCGIFADDR)."""
    import fcntl
    import socket
    import struct

    if not iface:
        return ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            packed = fcntl.ioctl(sock.fileno(), SIOCGIFADDR, struct.pack("256s", iface[:15].encode()))
    except OSError:
        return ""
    return socket.inet_ntoa(packed[20:24])
