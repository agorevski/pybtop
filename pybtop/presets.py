"""Preset string parsing ("cpu:1:default,proc:0:default cpu:0:block,net:0:tty")."""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_PRESETS = 9
VALID_BOXES = ("cpu", "mem", "net", "proc", "gpu0", "gpu1", "gpu2", "gpu3", "gpu4", "gpu5")
VALID_SYMBOLS = ("default", "braille", "block", "tty")


class PresetError(ValueError):
    pass


@dataclass
class PresetEntry:
    box: str
    position: int  # 0 = normal, 1 = alternate
    symbol: str  # "default" keeps the configured graph symbol


@dataclass
class Preset:
    entries: list[PresetEntry] = field(default_factory=list)

    def entry(self, box: str) -> PresetEntry | None:
        for item in self.entries:
            if item.box == box:
                return item
        return None

    @property
    def boxes(self) -> list[str]:
        return [e.box for e in self.entries]


def parse_preset_string(text: str) -> list[Preset]:
    """Parse the space-separated preset list. Raises PresetError on any invalid part."""
    presets: list[Preset] = []
    for chunk in text.split():
        preset = Preset()
        for raw in chunk.split(","):
            parts = raw.split(":")
            if len(parts) != 3:
                raise PresetError(f"malformed preset entry: {raw!r}")
            box, pos, symbol = parts
            if box not in VALID_BOXES:
                raise PresetError(f"invalid box name in presets: {box!r}")
            if pos not in ("0", "1"):
                raise PresetError("Invalid position value in config value presets!")
            if symbol not in VALID_SYMBOLS:
                raise PresetError("Invalid graph name in config value presets!")
            preset.entries.append(PresetEntry(box, int(pos), symbol))
        presets.append(preset)
    if len(presets) > MAX_PRESETS:
        raise PresetError("Too many presets entered!")
    return presets


def select_preset(presets: list[Preset], index: int) -> Preset | None:
    """1-based selection; indices past the end clamp to the last preset (btop behaviour)."""
    if not presets or index <= 0:
        return None
    return presets[min(index, len(presets)) - 1]
