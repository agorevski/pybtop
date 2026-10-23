"""Terminal input decoding: escape sequences, control keys, printable characters and SGR mouse reports."""

from __future__ import annotations

from dataclasses import dataclass

# CSI / SS3 sequences seen from xterm-compatible terminals.
_SEQUENCES = {
    "\x1b[A": "up", "\x1bOA": "up",
    "\x1b[B": "down", "\x1bOB": "down",
    "\x1b[C": "right", "\x1bOC": "right",
    "\x1b[D": "left", "\x1bOD": "left",
    "\x1b[H": "home", "\x1bOH": "home", "\x1b[1~": "home", "\x1b[7~": "home",
    "\x1b[F": "end", "\x1bOF": "end", "\x1b[4~": "end", "\x1b[8~": "end",
    "\x1b[5~": "pgup",
    "\x1b[6~": "pgdn",
    "\x1b[3~": "delete",
    "\x1bOP": "f1", "\x1b[11~": "f1",
    "\x1bOQ": "f2", "\x1b[12~": "f2",
}

_CONTROL = {
    "\r": "enter", "\n": "enter",
    "\x7f": "backspace", "\x08": "backspace",
    "\t": "tab", " ": "space",
    "\x03": "ctrl+c", "\x1a": "ctrl+z",
}

# Mouse button codes from SGR (mode 1006) reports that pybtop acts on, as btop 1.3.0 does.
_MOUSE_CLICK, _MOUSE_WHEEL_UP, _MOUSE_WHEEL_DOWN = 0, 64, 65


@dataclass(frozen=True)
class MouseEvent:
    """A mouse report. `kind` is 'click' (left press), 'scroll_up' or 'scroll_down'; col/row are 1-based."""

    kind: str
    col: int
    row: int


class KeyDecoder:
    """Turns raw stdin bytes into key names and MouseEvents.

    An incomplete escape sequence is held until more bytes arrive or `flush` is called.
    """

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, data: bytes) -> list[str | MouseEvent]:
        self._pending += data.decode("utf-8", errors="replace")
        keys: list[str | MouseEvent] = []
        buf = self._pending
        i = 0
        while i < len(buf):
            ch = buf[i]
            if ch == "\x1b":
                if buf.startswith("\x1b[<", i):
                    stop = _sgr_stop(buf, i + 3)
                    if stop is None:
                        break  # the SGR report is still arriving
                    if buf[stop] in "Mm":
                        event = _mouse_event(buf[i + 3 : stop], buf[stop])
                        if event is not None:
                            keys.append(event)
                        i = stop + 1
                    else:
                        i = stop  # malformed report: drop it, keep the byte that ended it
                    continue
                match = next((seq for seq in _SEQUENCES if buf.startswith(seq, i)), None)
                if match is not None:
                    keys.append(_SEQUENCES[match])
                    i += len(match)
                    continue
                if i + 1 == len(buf) or (buf[i + 1] in "[O" and not _complete_csi(buf, i)):
                    break  # wait for more bytes
                if buf[i + 1] == "[":
                    i = _csi_end(buf, i)  # drop an unrecognized but complete sequence
                    continue
                keys.append("esc")
                i += 1
                continue
            keys.append(_CONTROL.get(ch, ch))
            i += 1
        self._pending = buf[i:]
        return keys

    def flush(self) -> list[str | MouseEvent]:
        """Resolve a lone ESC after the input timeout. A partial CSI/SS3 sequence is dropped, not replayed as keys."""
        pending, self._pending = self._pending, ""
        if not pending:
            return []
        if pending == "\x1b":
            return ["esc"]
        if pending.startswith("\x1b["):
            return []
        if pending.startswith("\x1b"):
            return ["esc"] + [_CONTROL.get(c, c) for c in pending[1:]]
        return [_CONTROL.get(c, c) for c in pending]


def _sgr_stop(buf: str, start: int) -> int | None:
    """Index of the M/m that ends an SGR mouse report, or of the first byte that cannot belong to one.

    Returns None while the report is still incomplete.
    """
    for j in range(start, len(buf)):
        if buf[j] in "Mm":
            return j
        if not ("0" <= buf[j] <= "9" or buf[j] == ";"):
            return j
    return None


def _mouse_event(params: str, final: str) -> MouseEvent | None:
    """Decode the body of an SGR report ('button;col;row' + 'M' press / 'm' release)."""
    try:
        button, col, row = (int(part) for part in params.split(";"))
    except ValueError:
        return None
    if final != "M":
        return None  # releases are ignored, as in btop
    kinds = {_MOUSE_CLICK: "click", _MOUSE_WHEEL_UP: "scroll_up", _MOUSE_WHEEL_DOWN: "scroll_down"}
    if button not in kinds:
        return None
    return MouseEvent(kinds[button], col, row)


def _csi_end(buf: str, start: int) -> int:
    """Index just past the final byte of the CSI sequence starting at `start` (or len(buf))."""
    for j in range(start + 2, len(buf)):
        if "@" <= buf[j] <= "~":
            return j + 1
    return len(buf)


def _complete_csi(buf: str, start: int) -> bool:
    """True if buf[start:] already holds a final byte of a CSI sequence (ends with @-~)."""
    if buf[start + 1] != "[":
        return False
    return _csi_end(buf, start) <= len(buf) and any("@" <= c <= "~" for c in buf[start + 2 :])

