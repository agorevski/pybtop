"""Battery state from /sys/class/power_supply, following btop 1.3.0's get_battery (src/linux/btop_collect.cpp)."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

POWER_SUPPLY_DIR = "/sys/class/power_supply"


@dataclass
class BatteryInfo:
    percent: int
    seconds: int  # time to empty in seconds, -1 when unknown
    status: str  # lower case: charging, discharging, full, not charging or unknown


@dataclass
class _Supply:
    base: str
    device_type: str
    use_energy: bool
    energy_now: str | None
    energy_full: str | None
    power_now: str | None
    online: str | None


def _read(path: str, default: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return default


def _int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None


def _first_existing(paths: list[str]) -> str | None:
    return next((p for p in paths if os.path.exists(p)), None)


def _load_supply(base: str) -> _Supply | None:
    """Battery or UPS supplies that report themselves present, as btop's first scan does."""
    if not os.path.isdir(base):
        return None
    if _read(os.path.join(base, "present"), "") != "1":
        return None
    dev_type = _read(os.path.join(base, "type"), "")
    if dev_type not in ("Battery", "UPS"):
        return None

    energy_now = _first_existing([os.path.join(base, "energy_now"), os.path.join(base, "charge_now")])
    energy_full = _first_existing([os.path.join(base, "energy_full"), os.path.join(base, "charge_full")])
    use_energy = energy_now is not None and energy_full is not None
    if not use_energy and not os.path.exists(os.path.join(base, "capacity")):
        return None
    return _Supply(
        base=base,
        device_type=dev_type,
        use_energy=use_energy,
        energy_now=energy_now,
        energy_full=energy_full,
        power_now=_first_existing([os.path.join(base, "power_now"), os.path.join(base, "current_now")]),
        online=_first_existing([os.path.join(base, "AC0", "online"), os.path.join(base, "AC", "online")]),
    )


def _read_state(supply: _Supply) -> BatteryInfo | None:
    base = supply.base
    percent = -1
    if supply.use_energy:
        now = _int(_read(supply.energy_now, "-1"))
        full = _int(_read(supply.energy_full, "1"))
        if now is not None and full:
            percent = int(math.floor(100.0 * now / full + 0.5))
    if percent < 0:
        capacity = _int(_read(os.path.join(base, "capacity"), "-1"))
        percent = capacity if capacity is not None else -1
    if percent < 0:
        return None

    status = _read(os.path.join(base, "status"), "unknown").lower()
    if status == "unknown" and supply.online is not None:
        if _read(supply.online, "0") == "1":
            status = "charging" if percent < 100 else "full"
        else:
            status = "discharging"

    seconds = -1
    if status not in ("charging", "full"):
        if supply.use_energy and supply.power_now is not None:
            now = _int(_read(supply.energy_now, "0"))
            power = _int(_read(supply.power_now, "1"))
            if now is not None and power:
                seconds = int(round(float(now) / power * 3600))
        tte_path = os.path.join(base, "time_to_empty")
        if seconds < 0 and os.path.exists(tte_path):
            tte = _int(_read(tte_path, "0"))
            if tte is not None:
                seconds = tte * 60
    return BatteryInfo(percent=percent, seconds=seconds, status=status)


def read_battery(selected: str = "Auto", root: str = POWER_SUPPLY_DIR) -> BatteryInfo | None:
    """The selected battery (or the first Battery when 'Auto'); None when no usable battery exists."""
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return None
    supplies = {name: s for name in names if (s := _load_supply(os.path.join(root, name))) is not None}
    if not supplies:
        return None
    if selected in supplies:
        chosen = supplies[selected]
    else:
        batteries = [s for s in supplies.values() if s.device_type == "Battery"]
        chosen = batteries[0] if batteries else next(iter(supplies.values()))
    return _read_state(chosen)
