from __future__ import annotations

import math
from typing import Any

from matplotlib.axes import Axes


PANEL_BG = "#F8FAFC"
GRID = "#E5E7EB"
TEXT = "#111827"
MUTED = "#6B7280"
GREEN = "#16A34A"
BLUE = "#2563EB"
RED = "#DC2626"


def apply_ggplot_theme(ax: Axes, *, grid_axis: str = "y") -> None:
    ax.set_facecolor(PANEL_BG)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.9)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="both", colors=MUTED, labelsize=8.5)
    ax.title.set_color(TEXT)


def pct_color(value: Any) -> str:
    if value is None:
        return MUTED
    try:
        numeric = float(value)
        if math.isnan(numeric):
            return MUTED
        return GREEN if numeric >= 0 else RED
    except (TypeError, ValueError):
        return MUTED
