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
