from __future__ import annotations

import io
import os
import re
import tempfile
from numbers import Number
from pathlib import Path
from typing import Any

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "shu_tan_matplotlib")
)

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

from data_agent.visualization.formatting import format_axis_value, format_metric_value
from data_agent.visualization.policy import (
    ChartSpec,
    display_label,
    infer_chart_spec,
    load_chart_policy,
    metric_color,
)
from data_agent.visualization.recipes import (
    MONTHLY_MOM_STYLE,
    render_monthly_mom_sales_units,
)

_POLICY = load_chart_policy()
_THEME = _POLICY["theme"]
CHART_COLORS = [
    _THEME["palette"]["primary"],
    _THEME["palette"]["secondary"],
    _THEME["palette"]["warning"],
    _THEME["palette"]["purple"],
]
GRID_COLOR = _THEME["grid_color"]

ORDER_BY_RE = re.compile(r"\border\s+by\s+(.+?)(?:;|$)", re.IGNORECASE | re.DOTALL)
TREND_KEYWORDS = ("趋势", "走势", "trend", "daily", "每天", "每日", "按日")
TIME_COLUMN_HINTS = ("date", "day", "month", "week")


def _intent_hints() -> list[tuple[list[str], list[str]]]:
    """Load metric → column-substring hints from the centralized catalog.

    Returns a list ordered as authored in metric_synonyms.json (order matters:
    more specific phrases must come first so e.g. 广告销售 matches before 销售).
    """
    from data_agent.data_catalog import load_metric_synonyms

    return [
        (list(metric.get("question_keywords", [])), list(metric.get("column_substrings", [])))
        for metric in load_metric_synonyms().get("metrics", [])
    ]


def infer_metric_column(user_text: str, columns: list[str]) -> str | None:
    """Pick the result column that matches the metric the user asked about.

    Returns None if no keyword matches a column. Caller should fall back to
    SQL ORDER BY or the default numeric-column heuristic.
    """
    if not user_text or not columns:
        return None
    text = user_text.lower()
    norm_columns = [(col, col.lower()) for col in columns]
    for keywords, hints in _intent_hints():
        if any(kw.lower() in text for kw in keywords):
            for hint in hints:
                for col, col_lower in norm_columns:
                    if hint in col_lower:
                        return col
    return None


def parse_order_by_column(sql: str) -> str | None:
    """Extract the first column referenced in ORDER BY, normalized to match the
    final SELECT's column list (prefix-stripped, quotes removed)."""
    if not sql:
        return None
    match = ORDER_BY_RE.search(sql)
    if not match:
        return None
    first = re.split(r",", match.group(1), maxsplit=1)[0]
    first = re.sub(r"\b(?:asc|desc)\b", "", first, flags=re.IGNORECASE)
    first = re.sub(r"\bnulls\s+(?:first|last)\b", "", first, flags=re.IGNORECASE)
    first = first.strip().split(".")[-1].strip()
    first = first.strip('"`[]')
    return first or None
TEXT_COLOR = _THEME["text_color"]
MUTED_TEXT_COLOR = _THEME["muted_text_color"]


def _available_font_family() -> list[str]:
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in _THEME["font_family"]:
        if candidate in installed:
            return [candidate, "DejaVu Sans", "sans-serif"]
    return ["DejaVu Sans", "sans-serif"]


plt.rcParams["font.family"] = _available_font_family()
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.facecolor"] = _THEME["background_color"]
plt.rcParams["axes.facecolor"] = _THEME["background_color"]


def render_chart(
    data: list[dict[str, Any]],
    spec: ChartSpec,
) -> bytes | None:
    if spec.chart_type == "recipe" and spec.style == MONTHLY_MOM_STYLE:
        return render_monthly_mom_sales_units(data, spec)
    if spec.chart_type == "line" and spec.x_col and spec.y_cols:
        return generate_line_chart(data, x_col=spec.x_col, y_cols=list(spec.y_cols), title=spec.title)
    if spec.chart_type == "bar" and spec.x_col and spec.y_cols:
        chart = _POLICY["charts"].get(spec.style, _POLICY["charts"]["category_rank"])
        return generate_bar_chart(
            data,
            x_col=spec.x_col,
            y_col=spec.y_cols[0],
            title=spec.title,
            top_n=int(chart.get("top_n", 15)),
        )
    return None


def generate_table_image(
    data: list[dict[str, Any]],
    columns: list[str],
    title: str = "",
    max_rows: int | None = None,
) -> bytes:
    if not data or not columns:
        return _generate_empty_chart("暂无数据")

    rows = data if max_rows is None else data[:max_rows]
    cell_text = [
        [format_metric_value(row.get(column), column) for column in columns]
        for row in rows
    ]
    column_labels = [display_label(column) for column in columns]

    col_widths = [_column_width(label, [row[idx] for row in cell_text]) for idx, label in enumerate(column_labels)]
    total_width = sum(col_widths)
    fig_width = min(18.0, max(8.5, total_width * 0.17))
    fig_height = min(18.0, max(2.4, 1.15 + 0.42 * (len(cell_text) + 1)))

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=13, fontweight="bold", color=TEXT_COLOR, loc="left", pad=10)

    table = ax.table(
        cellText=cell_text,
        colLabels=column_labels,
        loc="upper left",
        cellLoc="left",
        colLoc="left",
        bbox=[0, 0, 1, 0.92 if title else 1],
        colWidths=[width / total_width for width in col_widths],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1, 1.25)

    header_bg = "#F3F4F6"
    zebra_bg = "#F9FAFB"
    border = "#D1D5DB"
    for (row_idx, _col_idx), cell in table.get_celld().items():
        cell.set_edgecolor(border)
        cell.set_linewidth(0.8)
        cell.PAD = 0.04
        if row_idx == 0:
            cell.set_facecolor(header_bg)
            cell.set_text_props(color=TEXT_COLOR, weight="bold")
        else:
            cell.set_facecolor("white" if row_idx % 2 else zebra_bg)
            cell.set_text_props(color=TEXT_COLOR)

    fig.tight_layout(pad=0.8)
    return _fig_to_png(fig)


def _column_width(label: str, values: list[str]) -> int:
    longest = max([len(label), *[len(str(value)) for value in values]], default=len(label))
    return max(8, min(26, longest + 2))


def generate_bar_chart(
    data: list[dict[str, Any]],
    x_col: str,
    y_col: str,
    title: str = "",
    x_label: str = "",
    y_label: str = "",
    top_n: int = 15,
) -> bytes:
    df = pd.DataFrame(data)
    if df.empty or x_col not in df.columns or y_col not in df.columns:
        return _generate_empty_chart("暂无数据")

    df = df.sort_values(y_col, ascending=False).head(top_n)
    df = df.iloc[::-1]
    chart = _POLICY["charts"]["category_rank"]
    fig_height = max(
        float(chart["min_height"]),
        min(float(chart["max_height"]), 1.2 + len(df) * float(chart["height_per_row"])),
    )
    fig, ax = plt.subplots(figsize=(float(chart["width"]), fig_height))
    bars = ax.barh(df[x_col].astype(str), df[y_col], color=metric_color(y_col), alpha=float(chart["bar_alpha"]))

    for bar in bars:
        width = bar.get_width()
        ax.annotate(
            format_metric_value(width, y_col),
            xy=(width, bar.get_y() + bar.get_height() / 2),
            xytext=(6, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=8.5,
            color=TEXT_COLOR,
        )

    _apply_axis_style(ax, grid_axis=chart.get("grid_axis", "x"))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: format_axis_value(value, y_col)))
    ax.set_title(title, fontsize=14, fontweight="bold", color=TEXT_COLOR, loc="left", pad=14)
    ax.set_xlabel(x_label or y_label or y_col, color=MUTED_TEXT_COLOR)
    ax.set_ylabel("")
    ax.tick_params(axis="y", labelsize=9, colors=TEXT_COLOR)
    ax.tick_params(axis="x", labelsize=8.5, colors=MUTED_TEXT_COLOR)
    ax.margins(x=0.16)
    fig.tight_layout(pad=1.5)
    return _fig_to_png(fig)


def generate_line_chart(
    data: list[dict[str, Any]],
    x_col: str,
    y_cols: list[str],
    title: str = "",
) -> bytes:
    df = pd.DataFrame(data)
    if df.empty or x_col not in df.columns:
        return _generate_empty_chart("暂无数据")

    df = df.sort_values(x_col)
    chart = _POLICY["charts"]["time_series"]
    fig, ax = plt.subplots(figsize=(float(chart["width"]), float(chart["height"])))
    for idx, y_col in enumerate([col for col in y_cols if col in df.columns]):
        ax.plot(
            df[x_col].astype(str),
            df[y_col],
            marker="o",
            label=display_label(y_col),
            color=metric_color(y_col) if len(y_cols) == 1 else CHART_COLORS[idx % len(CHART_COLORS)],
            linewidth=float(chart["line_width"]),
            markersize=float(chart["marker_size"]),
        )

    primary_y_col = next((col for col in y_cols if col in df.columns), "")
    _apply_axis_style(ax, grid_axis=chart.get("grid_axis", "y"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: format_axis_value(value, primary_y_col)))
    ax.set_title(title, fontsize=14, fontweight="bold", color=TEXT_COLOR, loc="left", pad=14)
    ax.legend(frameon=False, loc="upper left")
    ax.tick_params(axis="x", rotation=30, labelsize=8.5, colors=MUTED_TEXT_COLOR)
    ax.tick_params(axis="y", labelsize=8.5, colors=MUTED_TEXT_COLOR)
    fig.tight_layout(pad=1.5)
    return _fig_to_png(fig)


def data_to_markdown_table(
    data: list[dict[str, Any]], columns: list[str], max_rows: int = 10
) -> str:
    if not data:
        return "（无数据）"

    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows: list[str] = []
    for row in data[:max_rows]:
        cells = [format_metric_value(row.get(column), column) for column in columns]
        rows.append("| " + " | ".join(cells) + " |")

    output = "\n".join([header, separator, *rows])
    if len(data) > max_rows:
        output += f"\n\n*（仅显示前 {max_rows} 行，共 {len(data)} 行）*"
    return output


def choose_chart_columns(
    data: list[dict[str, Any]],
    columns: list[str],
    prefer_y: str | None = None,
) -> tuple[str, str] | None:
    if not data or len(columns) < 2:
        return None
    numeric_cols = [
        col
        for col in columns
        if any(
            isinstance(row.get(col), Number) and not isinstance(row.get(col), bool)
            for row in data[:5]
        )
    ]
    if not numeric_cols:
        return None
    x_col = next((col for col in columns if col not in numeric_cols), columns[0])
    if prefer_y and prefer_y in numeric_cols:
        return x_col, prefer_y
    return x_col, numeric_cols[-1]


def is_time_series_chart(user_text: str, x_col: str, row_count: int) -> bool:
    text = (user_text or "").lower()
    x_lower = (x_col or "").lower()
    if any(keyword in text for keyword in TREND_KEYWORDS):
        return True
    if row_count >= 3 and any(hint in x_lower for hint in TIME_COLUMN_HINTS):
        return True
    return False


def _generate_empty_chart(message: str) -> bytes:
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.text(
        0.5,
        0.5,
        message,
        ha="center",
        va="center",
        transform=ax.transAxes,
        color=MUTED_TEXT_COLOR,
        fontsize=12,
    )
    ax.axis("off")
    return _fig_to_png(fig)


def _apply_axis_style(ax, grid_axis: str = "x") -> None:
    ax.grid(axis=grid_axis, color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID_COLOR)
    ax.spines["bottom"].set_color(GRID_COLOR)


def _fig_to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
