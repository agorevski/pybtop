"""btop-style debug log, written only when --debug is given.

The file is btop.log in the config directory (btop keeps it next to btop.conf), one line per
message as `YYYY/MM/DD (HH:MM:SS) | LEVEL: text`. Nothing is ever written to the terminal.
"""

from __future__ import annotations

import os
import sys
import time

from . import config as config_mod

HEADER = "===> pybtop {version} (btop++ {btop} compatible)"

_fh = None
_started = 0.0


def is_enabled() -> bool:
    return _fh is not None


def open_log(version: str, btop_version: str, path: str | None = None) -> str | None:
    """Open btop.log for appending and write the session header. Returns the path, or None on failure."""
    global _fh, _started
    path = path or os.path.join(config_mod.config_dir(), "btop.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # btop separates sessions with a blank line.
        gap = os.path.isfile(path) and os.path.getsize(path) > 0
        _fh = open(path, "a", encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"Warning: could not open debug log {path}: {exc}\n")
        return None
    _started = time.monotonic()
    if gap:
        _fh.write("\n")
    _write(None, HEADER.format(version=version, btop=btop_version))
    return path


def debug(msg: str) -> None:
    _write("DEBUG", msg)


def info(msg: str) -> None:
    _write("INFO", msg)


def warning(msg: str) -> None:
    _write("WARNING", msg)


def error(msg: str) -> None:
    _write("ERROR", msg)


def close_session() -> None:
    """Log btop's exit line and close the file."""
    global _fh
    if _fh is None:
        return
    elapsed = int(time.monotonic() - _started)
    info(f"Quitting! Runtime: {elapsed // 3600:02d}:{elapsed // 60 % 60:02d}:{elapsed % 60:02d}")
    _fh.close()
    _fh = None


def _write(level: str | None, msg: str) -> None:
    if _fh is None:
        return
    stamp = time.strftime("%Y/%m/%d (%H:%M:%S)")
    prefix = f"{level}: " if level else ""
    try:
        _fh.write(f"{stamp} | {prefix}{msg}\n")
        _fh.flush()
    except OSError:
        pass
