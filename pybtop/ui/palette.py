"""Resolved colors for drawing, built from a Theme."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..render.ansi import Color, gradient_color
from ..theme import Theme

GRADIENT_NAMES = (
    "cpu", "temp", "free", "cached", "available", "used", "download", "upload", "process",
)


@dataclass
class Palette:
    bg: Color
    main_fg: Color
    title: Color
    hi_fg: Color
    selected_bg: Color
    selected_fg: Color
    inactive_fg: Color
    graph_text: Color
    meter_bg: Color
    div_line: Color
    box_colors: dict[str, Color] = field(default_factory=dict)
    gradients: dict[str, list[tuple[int, int, int]]] = field(default_factory=dict)

    @classmethod
    def from_theme(cls, theme: Theme, background: bool = True) -> "Palette":
        gradients = {name: theme.gradient(name) for name in GRADIENT_NAMES}
        return cls(
            bg=theme.color("main_bg") if background else None,
            main_fg=theme.color("main_fg"),
            title=theme.color("title"),
            hi_fg=theme.color("hi_fg"),
            selected_bg=theme.color("selected_bg"),
            selected_fg=theme.color("selected_fg"),
            inactive_fg=theme.color("inactive_fg"),
            graph_text=theme.color("graph_text"),
            meter_bg=theme.color("meter_bg"),
            div_line=theme.color("div_line"),
            box_colors={
                "cpu": theme.color("cpu_box"),
                "mem": theme.color("mem_box"),
                "net": theme.color("net_box"),
                "proc": theme.color("proc_box"),
            },
            gradients=gradients,
        )

    def box(self, name: str) -> Color:
        return self.box_colors.get(name, self.main_fg)

    def gradient_color(self, name: str, percent: float) -> Color:
        return gradient_color(self.gradients[name], percent)
