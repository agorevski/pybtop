"""Terminal input decoding: escape sequences, control keys and printable characters."""

from __future__ import annotations

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


class KeyDecoder:
    """Turns raw stdin bytes into key names. An incomplete escape sequence is held until `flush`."""

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, data: bytes) -> list[str]:
        self._pending += data.decode("utf-8", errors="replace")
        keys: list[str] = []
        buf = self._pending
        i = 0
        while i < len(buf):
            ch = buf[i]
            if ch == "\x1b":
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

    def flush(self) -> list[str]:
        """Resolve a lone ESC (or unknown sequence) after the input timeout."""
        pending, self._pending = self._pending, ""
        if not pending:
            return []
        if pending == "\x1b":
            return ["esc"]
        if pending.startswith("\x1b"):
            return ["esc"] + [_CONTROL.get(c, c) for c in pending[1:]]
        return [_CONTROL.get(c, c) for c in pending]


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

