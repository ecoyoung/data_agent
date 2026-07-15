from __future__ import annotations

from numbers import Number
from typing import Any


PERCENT_KEYWORDS = (
    "rate",
    "ratio",
    "percent",
    "percentage",
    "cvr",
    "conversion",
    "acos",
    "roas",
    "ctr",
    "tacos",
)
MONEY_KEYWORDS = ("sales", "revenue", "amount", "price", "cost", "spend")
COUNT_KEYWORDS = (
    "units",
    "quantity",
    "orders",
    "sessions",
    "clicks",
    "impressions",
    "views",
)


def metric_kind(column: str) -> str:
    normalized = column.lower()
    if any(keyword in normalized for keyword in PERCENT_KEYWORDS):
        return "percent"
    if any(keyword in normalized for keyword in COUNT_KEYWORDS):
        return "count"
    if any(keyword in normalized for keyword in MONEY_KEYWORDS):
        return "money"
    return "number"


def format_metric_value(value: Any, column: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)

    if isinstance(value, Number):
        kind = metric_kind(column)
        numeric = float(value)
        if kind == "percent":
            return f"{numeric * 100:,.2f}%"
        if kind == "money":
            return f"${numeric:,.2f}"
        if kind == "count":
            return f"{numeric:,.0f}"
        if isinstance(value, int):
            return f"{value:,}"
        return f"{value:,.2f}"

    return str(value).replace("|", "\\|")


def format_axis_value(value: float, column: str = "") -> str:
    kind = metric_kind(column)
    if kind == "percent":
        return f"{value * 100:.0f}%"
    if kind == "money":
        return f"${value:,.0f}"
    if kind == "count":
        return f"{value:,.0f}"
    return f"{value:,.0f}" if abs(value) >= 10 else f"{value:,.2f}"
