from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from numbers import Number
from pathlib import Path
from typing import Any


POLICY_PATH = Path(__file__).with_name("chart_policy.json")

DETAIL_KEYWORDS = (
    "明细",
    "列表",
    "表格",
    "原始",
    "detail",
    "list",
    "table",
)
DECLINE_KEYWORDS = ("decline", "drop", "decrease", "下滑", "下降", "减少")
TIME_COLUMN_HINTS = ("date", "day", "month", "week")


@dataclass(frozen=True)
class ChartSpec:
    chart_type: str
    x_col: str | None = None
    y_cols: tuple[str, ...] = ()
    style: str = "table"
    title: str = ""
    table_max_rows: int = 10
    meta: dict[str, Any] | None = None


@lru_cache(maxsize=1)
def load_chart_policy() -> dict[str, Any]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def numeric_columns(data: list[dict[str, Any]], columns: list[str]) -> list[str]:
    sample = data[:10]
    return [
        col
        for col in columns
        if any(isinstance(row.get(col), Number) and not isinstance(row.get(col), bool) for row in sample)
    ]


def dimension_columns(data: list[dict[str, Any]], columns: list[str]) -> list[str]:
    numeric = set(numeric_columns(data, columns))
    return [col for col in columns if col not in numeric]


def is_time_dimension(column: str) -> bool:
    lower = (column or "").lower()
    return any(hint in lower for hint in TIME_COLUMN_HINTS)


def is_detail_request(user_text: str) -> bool:
    text = (user_text or "").lower()
    return any(keyword in text for keyword in DETAIL_KEYWORDS)


def is_decline_metric(column: str, user_text: str = "") -> bool:
    text = f"{column} {user_text}".lower()
    return any(keyword in text for keyword in DECLINE_KEYWORDS)


def metric_color(column: str) -> str:
    policy = load_chart_policy()
    palette = policy["theme"]["palette"]
    lower = (column or "").lower()
    for rule in policy.get("metric_colors", []):
        if any(keyword in lower for keyword in rule.get("keywords", [])):
            return palette.get(rule.get("color", ""), palette["primary"])
    return palette["primary"]


def infer_chart_spec(
    *,
    user_text: str,
    data: list[dict[str, Any]],
    columns: list[str],
    prefer_y: str | None = None,
    preferred_chart: str = "auto",
    title: str = "",
) -> ChartSpec:
    policy = load_chart_policy()
    if not data or not columns:
        return ChartSpec(chart_type="table", style="table", title=title)

    from data_agent.visualization.recipes import match_monthly_mom_sales_units

    recipe = match_monthly_mom_sales_units(user_text, data, columns)
    if recipe is not None:
        return recipe

    nums = numeric_columns(data, columns)
    dims = dimension_columns(data, columns)

    if len(data) == 1 and len(nums) == 1 and len(columns) == 1:
        max_rows = int(policy["charts"]["kpi"]["max_rows"])
        return ChartSpec(chart_type="kpi", style="kpi", title=title, table_max_rows=max_rows)

    if is_detail_request(user_text) or preferred_chart == "table" or not nums:
        max_rows = int(policy["charts"]["table"]["max_rows"])
        return ChartSpec(chart_type="table", style="table", title=title, table_max_rows=max_rows)

    y_cols = _choose_y_columns(nums, prefer_y, preferred_chart)
    x_col = _choose_x_column(dims, columns, y_cols)
    if not x_col:
        max_rows = int(policy["charts"]["table"]["max_rows"])
        return ChartSpec(chart_type="table", style="table", title=title, table_max_rows=max_rows)

    if preferred_chart == "line" or _looks_like_time_series(user_text, x_col, len(data)):
        chart = policy["charts"]["time_series"]
        return ChartSpec(
            chart_type="line",
            x_col=x_col,
            y_cols=tuple(y_cols[: int(chart["max_series"])]),
            style="time_series",
            title=title or chart_title(x_col, y_cols[0]),
            table_max_rows=int(chart["max_table_rows"]),
        )

    if preferred_chart != "table":
        style = "diverging_rank" if is_decline_metric(y_cols[0], user_text) else "category_rank"
        chart = policy["charts"][style]
        return ChartSpec(
            chart_type="bar",
            x_col=x_col,
            y_cols=(y_cols[0],),
            style=style,
            title=title or chart_title(x_col, y_cols[0]),
            table_max_rows=int(policy["charts"]["table"]["max_rows"]),
        )

    return ChartSpec(chart_type="table", style="table", title=title)


def _choose_y_columns(
    numeric_cols: list[str],
    prefer_y: str | None,
    preferred_chart: str,
) -> list[str]:
    if prefer_y and prefer_y in numeric_cols:
        ordered = [prefer_y, *[col for col in numeric_cols if col != prefer_y]]
    else:
        ordered = list(numeric_cols)
    if preferred_chart == "line":
        return ordered
    return [ordered[-1]] if not prefer_y else [ordered[0]]


def _choose_x_column(dimension_cols: list[str], columns: list[str], y_cols: list[str]) -> str | None:
    if dimension_cols:
        return next((col for col in dimension_cols if is_time_dimension(col)), dimension_cols[0])
    return next((col for col in columns if col not in y_cols), None)


def _looks_like_time_series(user_text: str, x_col: str, row_count: int) -> bool:
    text = (user_text or "").lower()
    trend_keywords = ("趋势", "走势", "trend", "daily", "每天", "每日", "按日")
    if any(keyword in text for keyword in trend_keywords):
        return True
    return row_count >= 2 and is_time_dimension(x_col)


def chart_title(x_col: str, y_col: str) -> str:
    return f"{display_label(y_col)} by {display_label(x_col)}"


def display_label(column: str) -> str:
    normalized = (column or "").lower()
    labels = {
        "month": "Month",
        "report_date": "Date",
        "date": "Date",
        "day": "Day",
        "week": "Week",
        "asin": "ASIN",
        "sku": "SKU",
        "ordered_revenue": "Revenue",
        "revenue": "Revenue",
        "sales": "Sales",
        "br_sales": "BR Sales",
        "business_report_sales": "BR Sales",
        "ordered_units": "Units",
        "units": "Units",
        "order_items": "Order Items",
        "sessions": "Sessions",
        "ad_spend": "Ad Spend",
        "ams_spend": "Ad Spend",
        "ad_sales": "Ad Sales",
        "ams_sales": "Ad Sales",
        "acos": "ACoS",
        "tacos": "TACOS",
        "roas": "ROAS",
        "ctr": "CTR",
        "cvr": "CVR",
    }
    if normalized in labels:
        return labels[normalized]
    return " ".join(part.capitalize() for part in normalized.split("_") if part)
