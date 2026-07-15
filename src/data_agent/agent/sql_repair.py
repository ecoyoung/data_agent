from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from data_agent.agent.sql_checker import coerce_round_to_numeric, referenced_tables


CATALOG_DIR = Path(__file__).resolve().parent.parent / "data_catalog"


MONTH_TO_CHAR_ALIAS_RE = re.compile(
    r"\bto_char\s*\(\s*(?:[a-z_][a-z0-9_]*\.)?report_date\s*,\s*'yyyy-mm'\s*\)\s+as\s+month\b",
    re.IGNORECASE,
)
GROUP_BY_MONTH_ALIAS_RE = re.compile(r"\bGROUP\s+BY\s+month\b", re.IGNORECASE)
ORDER_BY_MONTH_ALIAS_RE = re.compile(r"\bORDER\s+BY\s+month\b", re.IGNORECASE)
TEXT_DATE_LITERAL_COMPARISON_RE = re.compile(
    r"(?<!:)\b((?:[a-z_][a-z0-9_]*\.)?report_date)\s*"
    r"(=|>=|<=|<|>)\s*(DATE\s*'[^']+')",
    re.IGNORECASE,
)
TEXT_DATE_LITERAL_IN_RE = re.compile(
    r"(?<!:)\b((?:[a-z_][a-z0-9_]*\.)?report_date)\s+IN\s*\(",
    re.IGNORECASE,
)
TEXT_DATE_LITERAL_BETWEEN_RE = re.compile(
    r"(?<!:)\b((?:[a-z_][a-z0-9_]*\.)?report_date)\s+BETWEEN\s+"
    r"(DATE\s*'[^']+')\s+AND\s+(DATE\s*'[^']+')",
    re.IGNORECASE,
)
SCOPE_IDENTITY_AND_FILTER_RE = re.compile(
    r"""
    (?P<prefix>\s+AND\s+)
    (?:
        LOWER\s*\(\s*(?P<lower_col>(?:[a-z_][a-z0-9_]*\.)?(?:brand|customer|customer_name|profile_name))\s*\)
        \s*=\s*
        (?:LOWER\s*\(\s*)?'(?P<lower_value>[^']+)'(?:\s*\))?
      |
        (?P<plain_col>(?:[a-z_][a-z0-9_]*\.)?(?:brand|customer|customer_name|profile_name))
        \s*=\s*
        (?:LOWER\s*\(\s*)?'(?P<plain_value>[^']+)'(?:\s*\))?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
INTERMEDIATE_SCOPE_PREFIXES = (
    "3p_sales_and_traffic",
    "3p_orders",
    "1p_orders",
    "ams_campaigns_placement",
    "ams_advertised_product",
    "ams_search_term",
    "ams_targeting",
    "ams_campaigns",
    "ams_audience",
    "ams_ad_campaign_time",
    "ams_advertised_time",
    "ams_time",
    "ads_sp_sd_advertised",
    "ads_dsp_campaign_ad",
    "ads_ad_campaign",
    "dsp_order_funnel",
    "dsp_audience_line",
    "dsp_audience_order",
    "dsp_creative_name",
    "dsp_lineitem_name",
    "dsp_product",
    "fba_inventory_days",
    "fba_returns",
    "search_term",
)


@dataclass(frozen=True)
class RepairResult:
    sql: str
    fixes: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.fixes)


@lru_cache
def _text_date_tables() -> set[str]:
    catalog_file = CATALOG_DIR / "tables_columns.json"
    if not catalog_file.exists():
        return set()
    data = json.loads(catalog_file.read_text(encoding="utf-8"))
    result: set[str] = set()
    for table_name, meta in data.get("tables", {}).items():
        date_field = str(meta.get("date_field") or "").lower()
        date_type = str(meta.get("date_field_type") or "").lower()
        if date_field == "report_date" and any(
            token in date_type for token in ("text", "character", "varchar", "char")
        ):
            result.add(str(table_name).lower())
    return result


def _references_text_report_date_table(sql: str) -> bool:
    tables = referenced_tables(sql)
    text_tables = _text_date_tables()
    return bool(tables & text_tables)


def _normalize_scope_value(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _scope_token_from_table(table_name: str) -> str | None:
    table = table_name.lower().split(".")[-1]
    if not table.startswith("intermediate_amazon_"):
        return None
    base = table.removeprefix("intermediate_amazon_")
    if base.endswith("_view"):
        base = base.removesuffix("_view")
    for prefix in sorted(INTERMEDIATE_SCOPE_PREFIXES, key=len, reverse=True):
        if base == prefix:
            return None
        if base.startswith(prefix + "_"):
            return base[len(prefix) + 1 :]
    return None


@lru_cache
def _scope_alias_values() -> dict[str, set[str]]:
    aliases_file = CATALOG_DIR / "scope_aliases.json"
    if not aliases_file.exists():
        return {}
    data = json.loads(aliases_file.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for scope, meta in data.get("scopes", {}).items():
        values = {scope}
        values.update(str(alias) for alias in meta.get("aliases", []))
        result[scope.lower()] = {_normalize_scope_value(value) for value in values if value}
    return result


def _scope_filter_values_for_sql(sql: str) -> set[str]:
    values: set[str] = set()
    aliases_by_scope = _scope_alias_values()
    for table in referenced_tables(sql):
        scope = _scope_token_from_table(table)
        if not scope:
            continue
        values.add(_normalize_scope_value(scope))
        values.update(aliases_by_scope.get(scope.lower(), set()))
    return values


def _remove_redundant_scope_identity_filters(sql: str) -> str:
    scope_values = _scope_filter_values_for_sql(sql)
    if not scope_values:
        return sql

    def replace(match: re.Match[str]) -> str:
        value = match.group("lower_value") or match.group("plain_value") or ""
        if _normalize_scope_value(value) in scope_values:
            return ""
        return match.group(0)

    return SCOPE_IDENTITY_AND_FILTER_RE.sub(replace, sql)


def _cast_text_report_date_comparisons(sql: str) -> str:
    if not _references_text_report_date_table(sql):
        return sql

    repaired = TEXT_DATE_LITERAL_COMPARISON_RE.sub(
        lambda match: f"{match.group(1)}::date {match.group(2)} {match.group(3)}",
        sql,
    )
    repaired = TEXT_DATE_LITERAL_IN_RE.sub(
        lambda match: f"{match.group(1)}::date IN (",
        repaired,
    )
    repaired = TEXT_DATE_LITERAL_BETWEEN_RE.sub(
        lambda match: f"{match.group(1)}::date BETWEEN {match.group(2)} AND {match.group(3)}",
        repaired,
    )
    return repaired


def repair_sql(sql: str) -> RepairResult:
    repaired = sql
    fixes: list[str] = []

    scope_filters_removed = _remove_redundant_scope_identity_filters(repaired)
    if scope_filters_removed != repaired:
        repaired = scope_filters_removed
        fixes.append("remove_redundant_scope_identity_filter")

    date_casted = _cast_text_report_date_comparisons(repaired)
    if date_casted != repaired:
        repaired = date_casted
        fixes.append("cast_text_report_date_to_date")

    rounded = coerce_round_to_numeric(repaired)
    if rounded != repaired:
        repaired = rounded
        fixes.append("coerce_round_to_numeric")

    if MONTH_TO_CHAR_ALIAS_RE.search(repaired):
        grouped = GROUP_BY_MONTH_ALIAS_RE.sub("GROUP BY 1", repaired)
        if grouped != repaired:
            repaired = grouped
            fixes.append("group_by_month_alias_to_position")

        ordered = ORDER_BY_MONTH_ALIAS_RE.sub("ORDER BY 1", repaired)
        if ordered != repaired:
            repaired = ordered
            fixes.append("order_by_month_alias_to_position")

    return RepairResult(sql=repaired, fixes=tuple(fixes))
