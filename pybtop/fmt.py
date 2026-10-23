"""Human-readable sizes, rates and percentages in the style btop uses."""

from __future__ import annotations

BINARY_UNITS = ("Byte", "KiB", "MiB", "GiB", "TiB", "PiB")
DECIMAL_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def _scale(value: float, base10: bool) -> tuple[float, str]:
    step = 1000.0 if base10 else 1024.0
    units = DECIMAL_UNITS if base10 else BINARY_UNITS
    idx = 0
    while value >= step and idx < len(units) - 1:
        value /= step
        idx += 1
    return value, units[idx]


def _three_digits(value: float) -> str:
    """Three significant characters, as in '13.0', '238', '1.78'."""
    if value >= 100:
        return f"{value:.0f}"
    if value >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def humanize_bytes(num: float, base10: bool = False) -> str:
    if num <= 0:
        return "0 Byte"
    value, unit = _scale(float(num), base10)
    if unit in ("Byte", "B"):
        return f"{int(value)} {unit}"
    return f"{_three_digits(value)} {unit}"


def humanize_rate(bytes_per_s: float, base10: bool = False) -> str:
    """Byte rate such as '8.72 KiB/s'."""
    if bytes_per_s <= 0:
        return f"0 {'B' if base10 else 'Byte'}/s"
    value, unit = _scale(float(bytes_per_s), base10)
    if unit in ("Byte", "B"):
        return f"{int(value)} {unit}/s"
    return f"{_three_digits(value)} {unit}/s"


def humanize_bits_rate(bytes_per_s: float, base10: bool = False) -> str:
    """Bit rate such as '167 Kibps' (bits per second, shown in parentheses by the net box)."""
    bits = bytes_per_s * 8.0
    if bits <= 0:
        return "0 bps"
    value, unit = _scale(bits, base10)
    unit_text = {
        "Byte": "bps", "B": "bps",
        "KiB": "Kibps", "KB": "Kbps", "MiB": "Mibps", "MB": "Mbps",
        "GiB": "Gibps", "GB": "Gbps", "TiB": "Tibps", "TB": "Tbps", "PiB": "Pibps", "PB": "Pbps",
    }[unit]
    return f"{_three_digits(value)} {unit_text}"


def format_percent(value: float) -> str:
    """Three-column percentage, e.g. '  5%' or '100%'."""
    return f"{min(100, round(value)):>3d}%"


def format_temperature(celsius: float, scale: str = "celsius") -> str:
    if scale == "fahrenheit":
        return f"{round(celsius * 9 / 5 + 32)}°F"
    if scale == "kelvin":
        return f"{round(celsius + 273.15)}K"
    if scale == "rankine":
        return f"{round((celsius + 273.15) * 9 / 5)}R"
    return f"{round(celsius)}°C"


_MEBI_BYTE = ("Byte", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB", "BiB", "GEB")
_MEBI_BIT = ("bit", "Kib", "Mib", "Gib", "Tib", "Pib", "Eib", "Zib", "Yib", "Bib", "GEb")
_MEGA_BYTE = ("Byte", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB", "BB", "GB")
_MEGA_BIT = ("bit", "Kb", "Mb", "Gb", "Tb", "Pb", "Eb", "Zb", "Yb", "Bb", "Gb")


def floating_humanizer(
    value: float,
    shorten: bool = False,
    start: int = 0,
    bit: bool = False,
    per_second: bool = False,
    base10: bool = False,
) -> str:
    """Port of btop's floating_humanizer (src/btop_tools.cpp:399-485); see docs/REVERSE_ENGINEERING.md."""
    mult = 8 if bit else 1
    if bit:
        units = _MEGA_BIT if base10 else _MEBI_BIT
    else:
        units = _MEGA_BYTE if base10 else _MEBI_BYTE
    v = int(value) * 100 * mult
    out = ""
    if base10:
        while v >= 100000:
            v //= 1000
            if v < 100:
                out = str(v)
                break
            start += 1
    else:
        while v >= 102400:
            v >>= 10
            if v < 100:
                out = str(v)
                break
            start += 1
    if not out:
        out = str(v)
        if not base10 and len(out) == 4 and start > 0:
            out = out[:-1]
            out = out[:2] + "." + out[2:]
        elif len(out) == 3 and start > 0:
            out = out[:1] + "." + out[1:]
        elif len(out) >= 2:
            out = out[:-2]
    if shorten:
        f_pos = out.find(".")
        if f_pos == 1 and len(out) > 3:
            out = f"{round(float(out) * 10) / 10:f}"[:3]
        elif f_pos != -1:
            out = str(c_round_int(float(out)))
        if len(out) > 3:
            out = str(int(out[0])) + ".0"
            start += 1
        out += units[start][0]
    else:
        out += " " + units[start]
    if per_second:
        out += "ps" if bit else "/s"
    return out


def c_round_int(value: float) -> int:
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def elapsed_text(seconds: int) -> str:
    """Process runtime as btop's detail panel shows it: 'HH:MM:SS', or 'Nd HH:MM' once a day has passed."""
    days, rest = divmod(max(0, seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    text = (f"{days}d " if days else "") + f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return text[:-3] if len(text) > 8 else text
