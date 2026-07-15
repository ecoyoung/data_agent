"""Column-level progressive disclosure for Text-to-SQL.

Given a user question and a table's structured metadata (from
tables_columns.json), pick the minimal set of columns the LLM needs to see.
Always includes date / business keys / required filters; adds metrics and
dimensions whose name or description matches the question, plus inputs to
any formula the user mentioned by name.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


CATALOG_DIR = Path(__file__).resolve().parent.parent / "data_catalog"
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")


@lru_cache
def load_tables_columns() -> dict[str, Any]:
    path = CATALOG_DIR / "tables_columns.json"
    if not path.exists():
        return {"tables": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def select_columns(
    user_text: str,
    table_name: str,
    table_meta: dict[str, Any],
    all_tables_meta: dict[str, Any] | None = None,
) -> set[str]:
    """Return the set of column names to expose for `table_name`.

    Selection layers (cumulative):
    1. Structural: date_field + business_keys + required_filters.
    2. Keyword-synonym match via metric_synonyms.json (question keyword →
       column substring).
    3. Token overlap between user_text and column name/description.
    4. Formula inputs: if user names a formula (acos / roas / ctr / ...),
       include its referenced columns.
    """
    selected: set[str] = set()

    # Layer 1: structural must-haves.
    date_field = table_meta.get("date_field")
    if date_field:
        selected.add(date_field)
    selected.update(table_meta.get("business_keys", []))
    selected.update(table_meta.get("required_filters", []))

    metric_cols = table_meta.get("metric_columns", {})
    dimension_cols = table_meta.get("dimension_columns", {})
    all_columns = {**metric_cols, **dimension_cols}

    if not user_text:
        return selected

    text_lower = user_text.lower()

    if any(token in text_lower for token in ("sp", "sd", "sb", "sponsored products", "sponsored brands", "sponsored display")):
        for ad_type_col in ("ams_type", "ads_type", "ad_type", "report_type"):
            if ad_type_col in all_columns:
                selected.add(ad_type_col)

    # Layer 2: synonym match (reuse centralized keyword → column-substring map).
    matched_substrings = _matched_column_substrings(text_lower)
    for col in all_columns:
        col_lower = col.lower()
        if any(sub in col_lower for sub in matched_substrings):
            selected.add(col)

    # Layer 3: token overlap.
    user_tokens = {t.lower() for t in _TOKEN_RE.findall(user_text) if len(t) >= 3}
    for col, desc in all_columns.items():
        col_tokens = {t.lower() for t in _TOKEN_RE.findall(col) if len(t) >= 3}
        if col_tokens & user_tokens:
            selected.add(col)
            continue
        # Chinese / mixed description match: substrings of length >= 2.
        desc_lower = desc.lower()
        for token in user_tokens:
            if token in desc_lower:
                selected.add(col)
                break

    # Layer 4: formula inputs.
    formulas = table_meta.get("formulas", {})
    for formula_name, formula_sql in formulas.items():
        if formula_name.lower() in text_lower:
            for ref in _TOKEN_RE.findall(formula_sql.lower()):
                if ref in all_columns:
                    selected.add(ref)

    return selected


def _matched_column_substrings(text_lower: str) -> set[str]:
    """Map question keywords to column-substring hints via metric_synonyms."""
    from data_agent.data_catalog import load_metric_synonyms

    substrings: set[str] = set()
    for metric in load_metric_synonyms().get("metrics", []):
        keywords = metric.get("question_keywords", [])
        if any(kw.lower() in text_lower for kw in keywords):
            substrings.update(metric.get("column_substrings", []))
    return substrings
