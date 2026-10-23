"""Sanitising untrusted text (process names, device labels) before it reaches the terminal."""

from __future__ import annotations

import unicodedata

REPLACEMENT = "?"


def printable(text: str) -> str:
    """Replace control, format and line/paragraph separator characters so no escape sequence survives.

    str.isprintable() is True for braille, box drawing, CJK and combining marks, so those pass through.
    Non-ASCII spaces become a plain space; everything else that is not printable becomes '?'.
    """
    if text.isprintable():
        return text
    out: list[str] = []
    for ch in text:
        if ch.isprintable():
            out.append(ch)
        elif unicodedata.category(ch) == "Zs":
            out.append(" ")
        else:
            out.append(REPLACEMENT)
    return "".join(out)
