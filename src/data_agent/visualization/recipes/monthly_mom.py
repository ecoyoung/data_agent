from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

from data_agent.visualization.formatting import format_axis_value, format_metric_value
from data_agent.visualization.policy import ChartSpec
from data_agent.visualization.recipes.theme import (
    BLUE,
    GRID,
    GREEN,
    MUTED,
    TEXT,
    apply_ggplot_theme,
    pct_color,
)


MONTHLY_MOM_STYLE = "monthly_mom_sales_units"


SALES_COLUMNS = ("sales", "revenue", "ordered_revenue", "order_revenue")
UNITS_COLUMNS = ("units", "ordered_units")
SALES_PCT_COLUMNS = ("sales_mom_change_pct", "sales_change_pct", "revenue_change_pct")
UNITS_PCT_COLUMNS = ("units_mom_change_pct", "units_change_pct")


def match_monthly_mom_sales_units(
    user_text: str,
    data: list[dict[str, Any]],
    columns: list[str],
) -> ChartSpec | None:
    if not data:
        return None
    column_set = {col.lower(): col for col in columns}
    month_col = column_set.get("month")
    sales_col = _first_present(column_set, SALES_COLUMNS)
    units_col = _first_present(column_set, UNITS_COLUMNS)
    sales_pct_col = _first_present(column_set, SALES_PCT_COLUMNS)
    units_pct_col = _first_present(column_set, UNITS_PCT_COLUMNS)
    if not all([month_col, sales_col, units_col, sales_pct_col, units_pct_col]):
        return None
    text = (user_text or "").lower()
    if "环比" not in text and "mom" not in text and not (sales_pct_col and units_pct_col):
        return None
    return ChartSpec(
        chart_type="recipe",
        x_col=month_col,
        y_cols=(sales_col, units_col),
        style=MONTHLY_MOM_STYLE,
        title="Monthly Sales and Units MoM",
        table_max_rows=12,
        meta={
            "sales_col": sales_col,
            "units_col": units_col,
            "sales_pct_col": sales_pct_col,
            "units_pct_col": units_pct_col,
        },
    )


def render_monthly_mom_sales_units(
    data: list[dict[str, Any]],
    spec: ChartSpec,
) -> bytes:
    from data_agent.visualization.chart import _fig_to_png

    month_col = spec.x_col or "month"
    meta = spec.meta or {}
    sales_col = str(meta.get("sales_col", spec.y_cols[0]))
    units_col = str(meta.get("units_col", spec.y_cols[1]))
    sales_pct_col = str(meta.get("sales_pct_col", "sales_mom_change_pct"))
    units_pct_col = str(meta.get("units_pct_col", "units_mom_change_pct"))

    df = pd.DataFrame(data).sort_values(month_col)
    x_values = df[month_col].astype(str).tolist()
    units_values = df[units_col].tolist()
    sales_values = df[sales_col].tolist()

    fig, ax_units = plt.subplots(figsize=(11.5, 6.2))
    ax_sales = ax_units.twinx()
    fig.patch.set_facecolor("white")
    ax_units.set_title(spec.title or "Monthly Sales and Units MoM", loc="left", fontsize=15, fontweight="bold", color=TEXT, pad=14)

    bars = ax_units.bar(x_values, units_values, color=BLUE, alpha=0.78, width=0.58, label="Units")
    line = ax_sales.plot(
        x_values,
        sales_values,
        color=GREEN,
        linewidth=2.4,
        marker="o",
        markersize=5.8,
        label="Sales",
        zorder=5,
    )

    apply_ggplot_theme(ax_units, grid_axis="y")
    ax_sales.set_facecolor("none")
    ax_sales.grid(False)
    ax_sales.spines["top"].set_visible(False)
    ax_sales.spines["left"].set_visible(False)
    ax_sales.spines["right"].set_color(GRID)
    ax_sales.tick_params(axis="y", colors=GREEN, labelsize=8.5)
    ax_sales.yaxis.set_major_formatter(FuncFormatter(lambda value, _: format_axis_value(value, sales_col)))

    ax_units.set_xlabel("")
    ax_units.set_ylabel("Units", color=BLUE, fontsize=9.5, fontweight="bold")
    ax_sales.set_ylabel("Sales", color=GREEN, fontsize=9.5, fontweight="bold")
    ax_units.tick_params(axis="x", rotation=0)
    ax_units.tick_params(axis="y", colors=BLUE)
    ax_units.yaxis.set_major_formatter(FuncFormatter(lambda value, _: format_axis_value(value, units_col)))

    unit_max = max([float(value or 0) for value in units_values] or [0])
    sales_max = max([float(value or 0) for value in sales_values] or [0])
    ax_units.set_ylim(0, unit_max * 1.28 if unit_max else 1)
    ax_sales.set_ylim(0, sales_max * 1.28 if sales_max else 1)

    unit_offset = unit_max * 0.035 if unit_max else 1
    for idx, bar in enumerate(bars):
        value = units_values[idx]
        pct = df.iloc[idx].get(units_pct_col)
        ax_units.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() - unit_offset * 0.8,
            format_metric_value(value, units_col),
            ha="center",
            va="top",
            fontsize=8.2,
            fontweight="bold",
            color="white",
        )
        ax_units.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() - unit_offset * 2.35,
            "" if pd.isna(pct) else format_metric_value(pct, units_pct_col),
            ha="center",
            va="top",
            fontsize=8.2,
            fontweight="bold",
            color="white",
        )

    sales_offset = sales_max * 0.035 if sales_max else 1
    for idx, value in enumerate(sales_values):
        pct = df.iloc[idx].get(sales_pct_col)
        ax_sales.text(
            idx,
            float(value or 0) + sales_offset * 0.9,
            format_metric_value(value, sales_col),
            ha="center",
            va="bottom",
            fontsize=8.2,
            color=TEXT,
        )
        ax_sales.text(
            idx,
            float(value or 0) + sales_offset * 2.35,
            "" if pd.isna(pct) else format_metric_value(pct, sales_pct_col),
            ha="center",
            va="bottom",
            fontsize=8.2,
            fontweight="bold",
            color=pct_color(pct),
        )

    legend_items = [bars, line[0]]
    ax_units.legend(
        legend_items,
        ["Units", "Sales"],
        loc="upper center",
        bbox_to_anchor=(0.5, 1.02),
        ncol=2,
        frameon=False,
        fontsize=9,
    )
    fig.text(0.055, 0.025, "Bars use the left axis; the sales line uses the right axis. MoM labels show month-over-month change.", fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.08, right=0.91, top=0.86, bottom=0.13)
    return _fig_to_png(fig)


def _first_present(column_set: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in column_set:
            return column_set[candidate]
    return None
