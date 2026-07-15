from __future__ import annotations

import json
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from data_agent.agent.intent import render_intent_prompt
from data_agent.data_catalog import render_catalog_rules_for_prompt


_SEMANTIC_ASCII_RE = re.compile(r"[a-z0-9_]{2,}")
_SEMANTIC_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


CATALOG_DIR = Path(__file__).resolve().parent.parent / "data_catalog"
TABLE_DOCS: dict[str, str] = {}
DOC_ORDER = {
    "intermediate_amazon.md": -1,
}


def _doc_for_table(table: dict[str, Any]) -> str | None:
    doc = table.get("doc")
    if doc:
        return str(doc)
    table_name = str(table.get("table", ""))
    if table_name.startswith("intermediate_amazon_"):
        return "intermediate_amazon.md"
    return TABLE_DOCS.get(table_name)


def _table_doc_mapping(metadata: dict[str, Any] | None = None) -> dict[str, str]:
    mapping = dict(TABLE_DOCS)
    metadata = metadata or _load_table_metadata()
    for table in metadata.get("tables", []):
        table_name = table.get("table")
        doc = _doc_for_table(table)
        if table_name and doc:
            mapping[str(table_name)] = doc
    return mapping


def _read(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _inject_current_dates(text: str) -> str:
    """Replace {{TODAY}} / {{YESTERDAY}} placeholders with current dates.

    Keeps the system prompt's date rules in sync with the actual calendar so
    relative phrases like '昨天' / '最近 7 天' resolve correctly.
    """
    if not text:
        return text
    today = date.today()
    return (
        text.replace("{{TODAY}}", today.isoformat())
        .replace("{{YESTERDAY}}", (today - timedelta(days=1)).isoformat())
    )


def _load_table_metadata() -> dict[str, Any]:
    metadata_file = CATALOG_DIR / "tables_metadata.json"
    if not metadata_file.exists():
        return {}
    return json.loads(metadata_file.read_text(encoding="utf-8"))


def _load_scope_aliases() -> dict[str, Any]:
    aliases_file = CATALOG_DIR / "scope_aliases.json"
    if not aliases_file.exists():
        return {"scopes": {}}
    return json.loads(aliases_file.read_text(encoding="utf-8"))


@lru_cache
def _load_table_semantic_index() -> dict[str, Any]:
    index_file = CATALOG_DIR / "table_semantic_index.json"
    if not index_file.exists():
        return {"tables": {}}
    return json.loads(index_file.read_text(encoding="utf-8"))


def _semantic_tokens(text: str) -> set[str]:
    """Tokenize a user query in the same lightweight style as PD-4-lite index."""
    text = str(text or "").lower()
    tokens: set[str] = set()

    for match in _SEMANTIC_ASCII_RE.finditer(text):
        raw = match.group(0)
        tokens.add(raw)
        if "_" in raw:
            tokens.update(part for part in raw.split("_") if len(part) >= 2)

    for match in _SEMANTIC_CJK_RE.finditer(text):
        raw = match.group(0)
        if len(raw) <= 8:
            tokens.add(raw)
        if len(raw) >= 2:
            tokens.update(raw[i : i + 2] for i in range(len(raw) - 1))

    return tokens


def _semantic_score_table(table_name: str, query: str) -> int:
    """Return a capped supplemental score from the local semantic index.

    This is intentionally small: exact table/scope/domain matches remain the
    primary routing signal, while the semantic index helps long-tail language
    such as "营收" or "GMV" reach the order revenue tables.
    """
    table_index = _load_table_semantic_index().get("tables", {}).get(table_name)
    if not table_index:
        return 0

    tokens = _semantic_tokens(query)
    if not tokens:
        return 0

    weights = table_index.get("tokens", {})
    raw_score = sum(float(weights.get(token, 0)) for token in tokens)
    if raw_score <= 0:
        return 0

    normalized = raw_score / max(float(table_index.get("norm", 1.0)), 1.0)
    return min(18, int(raw_score // 4) + int(normalized * 10))


def _metadata_summary(
    metadata: dict[str, Any],
    selected_tables: set[str] | None = None,
) -> str:
    """Render the per-table metadata block for the system prompt.

    If ``selected_tables`` is None, include every cataloged table. Otherwise
    include only the listed tables (plus a count of how many were filtered out
    so the LLM knows other tables exist but does not see their fields).
    """
    if not metadata:
        return ""

    all_tables = metadata.get("tables", [])
    if selected_tables is None:
        filtered = all_tables
        omitted_count = 0
    else:
        filtered = [t for t in all_tables if t.get("table") in selected_tables]
        omitted_count = len(all_tables) - len(filtered)

    rows = []
    for table in filtered:
        rows.append(
            {
                "table": table.get("table"),
                "domain": table.get("domain"),
                "keywords": table.get("keywords", []),
                "date_field": table.get("date_field"),
                "latest_business_date": table.get("latest_business_date"),
                "indexed_columns": table.get("indexed_columns", []),
                "use_when": table.get("use_when"),
                "avoid_when": table.get("avoid_when"),
            }
        )

    payload: dict[str, Any] = {
        "scope": metadata.get("scope"),
        "default_filters": metadata.get("default_filters", {}),
        "tables": rows,
    }
    if omitted_count:
        payload["omitted_tables_count"] = omitted_count
        payload["note"] = (
            f"{omitted_count} other cataloged tables are filtered out for this "
            "turn; if the user asks about a different business area, request "
            "those tables in a follow-up instead of guessing fields."
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _text_from_history(session_history: list[dict], new_user_message: str) -> str:
    recent = [
        str(item.get("content", ""))
        for item in session_history[-6:]
        if item.get("role") == "user" and item.get("content")
    ]
    recent.append(new_user_message)
    return "\n".join(recent).lower()


def _domain_hints() -> dict[str, list[str]]:
    """Load domain → keyword hints from the centralized catalog."""
    from data_agent.data_catalog import load_metric_synonyms

    return {
        entry["domain"]: list(entry.get("question_keywords", []))
        for entry in load_metric_synonyms().get("table_domains", [])
        if entry.get("domain")
    }


INTERMEDIATE_FAMILY_PREFIXES = (
    "1p_orders",
    "3p_orders",
    "3p_sales_and_traffic",
    "ads_ad_campaign",
    "ads_dsp_campaign_ad",
    "ads_sp_sd_advertised",
    "ams_ad_campaign_time",
    "ams_advertised_product",
    "ams_advertised_time",
    "ams_audience",
    "ams_campaigns_placement",
    "ams_campaigns",
    "ams_search_term",
    "ams_targeting",
    "ams_time",
    "dsp_audience_line",
    "dsp_audience_order",
    "dsp_creative_name",
    "dsp_lineitem_name",
    "dsp_order_funnel",
    "dsp_product",
    "fba_inventory_days",
    "fba_returns",
    "search_term",
)


def _intermediate_scope_token(table_name: str) -> str:
    if not table_name.startswith("intermediate_amazon_"):
        return ""
    base = table_name.removeprefix("intermediate_amazon_").removesuffix("_view")
    for prefix in sorted(INTERMEDIATE_FAMILY_PREFIXES, key=len, reverse=True):
        if base == prefix:
            return ""
        if base.startswith(prefix + "_"):
            return base[len(prefix) + 1 :]
    return ""


def _scope_alias_score(scope_token: str, query: str, compact_query: str) -> int:
    if not scope_token:
        return 0
    scopes = _load_scope_aliases().get("scopes", {})
    scope = scopes.get(scope_token, {})
    aliases = scope.get("aliases", [])
    score = 0
    for alias in aliases:
        alias_text = str(alias).lower()
        compact_alias = alias_text.replace(" ", "").replace("-", "").replace("_", "")
        if alias_text and alias_text in query:
            score = max(score, 24)
        if compact_alias and compact_alias in compact_query:
            score = max(score, 22)
    return score


def _score_table(table: dict[str, Any], query: str) -> int:
    domain_hints = _domain_hints()
    score = 0
    table_name = str(table.get("table", "")).lower()
    domain = str(table.get("domain", "")).lower()
    normalized_table_name = table_name.replace("_", " ")
    compact_query = query.replace(" ", "").replace("-", "").replace("_", "")
    scope_token = str(table.get("scope_token") or _intermediate_scope_token(table_name))
    compact_scope = scope_token.replace("_", "")
    explicit_sp = any(hint in query for hint in domain_hints.get("sp", []))
    explicit_sb = any(hint in query for hint in domain_hints.get("sb", []))
    generic_sales = any(term in query for term in ("销售额", "营收", "收入", "gmv", "revenue"))
    explicit_business_report = any(
        term in query
        for term in ("business report", "sessions", "session", "page views", "流量", "转化率", "购物车")
    )

    if table_name in query:
        score += 12
    if normalized_table_name in query:
        score += 10
    if table_name.replace("_", "") in compact_query:
        score += 10
    if compact_scope and compact_scope in compact_query:
        score += 20
    if scope_token and scope_token.replace("_", " ") in query:
        score += 16
    score += _scope_alias_score(scope_token, query, compact_query)
    if domain and domain.replace("_", " ") in query:
        score += 5

    for keyword in table.get("keywords", []):
        keyword_text = str(keyword).lower()
        if keyword_text and keyword_text in query:
            score += 4

    for hint_domain, hints in domain_hints.items():
        if any(hint in query for hint in hints):
            if hint_domain == domain or domain.startswith(hint_domain) or hint_domain in domain:
                score += 3

    # Disambiguate common Amazon ad language for intermediate AMS/DSP tables.
    if (explicit_sp or explicit_sb or "广告" in query or "ams" in query) and "intermediate_amazon_ams_" in table_name:
        score += 6
    if "dsp" in query and "intermediate_amazon_dsp_" in table_name:
        score += 10
    if ("campaign" in query or "活动" in query) and domain == "ams_campaigns":
        score += 14
    if ("advertised product" in query or "广告商品" in query or "广告asin" in query) and domain == "ams_advertised_product":
        score += 14
    if ("targeting" in query or "投放词" in query) and domain == "ams_targeting":
        score += 14
    if ("placement" in query or "广告位" in query) and domain == "ams_placement":
        score += 14
    if "tacos" in query:
        if table_name.startswith("intermediate_amazon_3p_orders_"):
            score += 10
        if table_name.startswith("intermediate_amazon_ams_campaigns_"):
            score += 10
    if generic_sales and not explicit_business_report:
        if table_name.startswith("intermediate_amazon_3p_orders_"):
            score += 10
    if "business report" in query and (
        table_name.startswith("intermediate_amazon_3p_sales_and_traffic_")
    ):
        score += 10
    if ("sessions" in query or "转化率" in query) and (
        table_name.startswith("intermediate_amazon_3p_sales_and_traffic_")
    ):
        score += 6
    if "搜索词" in query or "search term" in query:
        if "search_term" in table_name:
            score += 8
        elif "targeting" in table_name:
            score -= 3
    if "补货" in query and table_name.startswith("intermediate_amazon_fba_inventory_days_"):
        score += 8
    if "退货" in query and (
        table_name.startswith("intermediate_amazon_fba_returns_")
    ):
        score += 8

    score += _semantic_score_table(table_name, query)

    return score


def select_catalog_table_docs(
    new_user_message: str,
    session_history: list[dict] | None = None,
    max_docs: int = 4,
) -> list[str]:
    metadata = _load_table_metadata()
    tables = metadata.get("tables", [])
    if not tables:
        return []

    query = _text_from_history(session_history or [], new_user_message)
    scored = [
        (_score_table(table, query), table)
        for table in tables
        if table.get("select_permission") is True
    ]
    matches = [table for score, table in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]

    docs: list[str] = []
    for table in matches:
        doc = _doc_for_table(table)
        if doc and doc not in docs:
            docs.append(doc)
        if len(docs) >= max_docs:
            break

    if not docs and any(
        str(table.get("table", "")).startswith("intermediate_amazon_")
        for table in tables
        if table.get("select_permission") is True
    ):
        docs.append("intermediate_amazon.md")

    return sorted(docs, key=lambda doc: DOC_ORDER.get(doc, 99))


def _tables_referenced_by_docs(selected_table_docs: list[str] | None) -> set[str] | None:
    """Return the set of catalog tables whose docs are in ``selected_table_docs``.

    Returns None when no filter is applied (load every doc), so callers can
    distinguish "all docs" from "no docs matched".
    """
    if selected_table_docs is None:
        return None
    mapping = _table_doc_mapping()
    return {
        table_name
        for table_name, doc_name in mapping.items()
        if doc_name in selected_table_docs
    }


def _render_selected_tables(
    parts: list[str],
    selected_table_docs: list[str] | None,
    selected_tables: set[str] | None,
    user_text: str,
) -> bool:
    """Render compact per-table schema blocks for tables present in
    tables_columns.json. Returns True if at least one table was rendered.

    Within the doc-selected pool, tables are re-scored against the question
    and only the top few are rendered — loading every SP/SB table just
    because the SP/SB doc was selected would defeat the column-pruning goal.
    """
    from data_agent.agent.column_selector import load_tables_columns

    catalog = load_tables_columns()
    tables_catalog = catalog.get("tables", {})
    if not tables_catalog:
        return False

    candidate_tables = (
        sorted(selected_tables & set(tables_catalog.keys()))
        if selected_tables is not None
        else sorted(tables_catalog.keys())
    )
    if not candidate_tables:
        return False

    table_names = _refine_top_tables(candidate_tables, user_text)
    if not table_names:
        return False

    rendered = False
    for table_name in table_names:
        table_meta = tables_catalog[table_name]
        rendered_block = _render_one_table(table_name, table_meta, user_text)
        if rendered_block:
            parts.append(f"\n\n## {table_name}\n")
            parts.append(rendered_block)
            rendered = True
    return rendered


def _snake_case_tokens(text: str) -> set[str]:
    """Split on underscores and non-alphanumeric, return lower-case tokens
    of length >= 3. Used to match user-text against snake_case column names
    (e.g. 'advertised_asin' → {'advertised', 'asin'})."""
    parts = re.split(r"[^A-Za-z0-9]+", text)
    return {p.lower() for p in parts if len(p) >= 3}


def _refine_top_tables(
    candidate_tables: list[str],
    user_text: str,
    max_tables: int = 3,
) -> list[str]:
    """Within a doc-selected pool, rank tables by question relevance and
    return the top few. Falls back to all candidates when scoring is
    inconclusive (e.g. user_text is empty)."""
    if not user_text or not candidate_tables:
        return list(candidate_tables)

    from data_agent.agent.column_selector import load_tables_columns

    metadata = _load_table_metadata()
    metadata_tables = {t.get("table"): t for t in metadata.get("tables", []) if t.get("table")}
    columns_catalog = load_tables_columns().get("tables", {})
    query = user_text.lower()
    text_tokens = _snake_case_tokens(user_text)

    scored: list[tuple[int, str]] = []
    for table_name in candidate_tables:
        meta = metadata_tables.get(table_name, {})
        score = _score_table(meta, query)
        # Strong prior: if the table name itself appears in the question,
        # always keep it.
        if table_name.lower().replace("_innerbrightness", "") in query:
            score += 50

        # Business-key match: if the question references ASIN/SKU/etc. and
        # this table exposes those as business keys, it's almost certainly
        # the right grain. E.g. "广告花费最多的 ASIN" → advertised_product
        # (business_key advertised_asin) over campaigns (no ASIN grain).
        table_cols_meta = columns_catalog.get(table_name, {})
        for key in table_cols_meta.get("business_keys", []):
            key_tokens = _snake_case_tokens(key)
            if key_tokens & text_tokens:
                score += 8

        scored.append((score, table_name))

    scored.sort(key=lambda item: (-item[0], item[1]))

    # Always keep at least one table; cap at max_tables; if multiple tables
    # tie at the boundary, include them too (better to over-reveal slightly).
    if not scored:
        return list(candidate_tables)
    top_score = scored[0][0]
    score_floor = max(1, top_score - 4)
    result = [name for score, name in scored if score >= score_floor]
    # De-duplicate while preserving order, then cap.
    seen: set[str] = set()
    final: list[str] = []
    for name in result:
        if name in seen:
            continue
        seen.add(name)
        final.append(name)
        if len(final) >= max_tables:
            break
    return final or list(candidate_tables)


def _render_one_table(
    table_name: str, table_meta: dict[str, Any], user_text: str
) -> str:
    """Compact DDL-like rendering with question-relevant column pruning."""
    from data_agent.agent.column_selector import select_columns

    lines: list[str] = []

    purpose = table_meta.get("purpose")
    if purpose:
        lines.append(f"- 用途: {purpose}")

    grain = table_meta.get("grain")
    if grain:
        lines.append(f"- 粒度: {grain}")

    date_field = table_meta.get("date_field")
    date_cast = table_meta.get("date_cast_hint")
    if date_field:
        lines.append(f"- 日期字段: `{date_field}`" + (f"（{date_cast}）" if date_cast else ""))

    default_values = table_meta.get("default_filter_values") or {}
    required = table_meta.get("required_filters") or []
    if required:
        filter_parts = [
            f"{col}='{default_values[col]}'" for col in required if default_values.get(col)
        ]
        optional_filters = [col for col in required if not default_values.get(col)]
        if filter_parts:
            lines.append("- 默认过滤: " + ", ".join(filter_parts))
        if optional_filters:
            lines.append(
                "- 可选过滤字段: "
                + ", ".join(optional_filters)
                + "（不要猜值；表名 scope 已经限定品牌/店铺，只有用户明确给出字段值时才过滤）"
            )

    selected = select_columns(user_text, table_name, table_meta)
    metric_cols = table_meta.get("metric_columns", {})
    dimension_cols = table_meta.get("dimension_columns", {})

    selected_metrics = sorted(selected & set(metric_cols.keys()))
    selected_dimensions = sorted(selected & set(dimension_cols.keys()))

    if selected_metrics:
        lines.append("- 命中指标列:")
        for col in selected_metrics:
            lines.append(f"  - `{col}`: {metric_cols[col]}")
    if selected_dimensions:
        lines.append("- 命中维度列:")
        for col in selected_dimensions:
            lines.append(f"  - `{col}`: {dimension_cols[col]}")

    rules = table_meta.get("business_rules") or []
    if rules:
        lines.append("- 业务规则:")
        for rule in rules:
            lines.append(f"  - {rule}")

    # Only show formulas whose name appears in the question (avoids dumping
    # every formula template every turn).
    formulas = table_meta.get("formulas") or {}
    text_lower = user_text.lower()
    relevant_formulas = {
        name: sql
        for name, sql in formulas.items()
        if name.lower() in text_lower
    }
    if relevant_formulas:
        lines.append("- 相关公式:")
        for name, sql in relevant_formulas.items():
            lines.append(f"  - `{name}`: {sql}")

    example = table_meta.get("example")
    if example and user_text:
        # Only include the example when there's a user question; in the
        # "no filter" path (e.g. tests) we skip it to keep the block short.
        lines.append(f"- 示例: `{example}`")

    return "\n".join(lines)


def _load_relationship_examples_if_relevant(
    selected_table_docs: list[str] | None,
) -> str | None:
    """Load cross-domain SQL examples for the intermediate Amazon catalog."""
    if selected_table_docs is None:
        # No filter applied (e.g. test invocation) → keep historical behavior.
        return _read(CATALOG_DIR / "relationships_examples.md")

    docs = set(selected_table_docs)
    if "intermediate_amazon.md" in docs:
        return _read(CATALOG_DIR / "relationships_examples.md")
    return None


def load_data_catalog(
    selected_table_docs: list[str] | None = None,
    user_text: str = "",
    explicit_selected_tables: set[str] | None = None,
) -> str:
    parts: list[str] = []

    system_prompt = CATALOG_DIR / "system_prompt.md"
    content = _read(system_prompt)
    if content:
        parts.append(_inject_current_dates(content))

    if user_text:
        parts.append("\n\n" + render_intent_prompt(user_text))

    structured_rules = render_catalog_rules_for_prompt()
    if structured_rules:
        parts.append("\n\n" + structured_rules)

    metadata = _load_table_metadata()
    selected_tables = explicit_selected_tables or _tables_referenced_by_docs(selected_table_docs)
    if selected_tables is not None and len(selected_tables) > 12:
        selected_tables = set(_refine_top_tables(sorted(selected_tables), user_text, max_tables=6))
    metadata_summary = _metadata_summary(metadata, selected_tables=selected_tables)
    if metadata_summary:
        parts.append("\n\n# ===== Data Catalog: table metadata =====")
        parts.append(metadata_summary)

    parts.append("\n\n# ===== Data Catalog: tables =====")
    rendered_any_table = _render_selected_tables(
        parts, selected_table_docs, selected_tables, user_text
    )
    if not rendered_any_table:
        # No JSON catalog entries hit; load full .md docs as the historical fallback.
        tables_dir = CATALOG_DIR / "tables"
        if tables_dir.exists():
            table_files = (
                [tables_dir / name for name in selected_table_docs]
                if selected_table_docs is not None
                else sorted(tables_dir.glob("*.md"))
            )
            for table_file in table_files:
                content = _read(table_file)
                if content:
                    parts.append(f"\n\n# ===== Table document: {table_file.name} =====")
                    parts.append(content)

    relationships = CATALOG_DIR / "relationships.md"
    content = _read(relationships)
    if content:
        parts.append("\n\n# ===== Data Catalog: relationships =====")
        parts.append(content)

    examples = _load_relationship_examples_if_relevant(selected_table_docs)
    if examples:
        parts.append("\n\n# ===== Data Catalog: cross-domain examples =====")
        parts.append(examples)

    templates = _read(CATALOG_DIR / "query_templates.md")
    if templates:
        parts.append("\n\n# ===== Data Catalog: high-frequency query templates =====")
        parts.append(templates)

    if not parts:
        return (
            "你是一个 PostgreSQL 数据查询助手。只能生成只读 SELECT SQL；"
            "如果缺少表结构、字段、时间范围或业务口径，必须先追问。"
        )

    return "\n\n".join(parts)


def build_messages(
    session_history: list[dict],
    new_user_message: str,
    selected_tables: list[str] | None = None,
    few_shot_examples: list[dict] | None = None,
) -> list[dict]:
    """Compose the message list for the SQL-generation LLM call.

    Parameters
    ----------
    selected_tables:
        Optional pre-refined table list (e.g. from PD-2 LLM re-selection).
        When provided, overrides the keyword-based doc→table derivation.
    few_shot_examples:
        Optional list of ``{"question": ..., "sql": ...}`` dicts from past
        successful queries (PD-5). Rendered at the end of the system prompt.
    """
    selected_table_docs = select_catalog_table_docs(new_user_message, session_history)
    explicit_selected = set(selected_tables) if selected_tables else None
    system_prompt = load_data_catalog(
        selected_table_docs,
        user_text=new_user_message,
        explicit_selected_tables=explicit_selected,
    )
    if few_shot_examples:
        system_prompt = system_prompt + _format_few_shot(few_shot_examples)
    return [
        {"role": "system", "content": system_prompt},
        *session_history,
        {"role": "user", "content": new_user_message},
    ]


def _format_few_shot(examples: list[dict]) -> str:
    """Render past successful question/SQL pairs as a compact reference block."""
    if not examples:
        return ""
    lines = ["\n\n# ===== 参考历史问题（仅作格式参考，不要照抄口径） ====="]
    for idx, ex in enumerate(examples, start=1):
        question = (ex.get("question") or "").strip().replace("\n", " ")
        sql = (ex.get("sql") or "").strip()
        if not question or not sql:
            continue
        lines.append(f"\n## 参考 {idx}\n问题：{question}\n```sql\n{sql}\n```")
    return "\n".join(lines)


def refine_tables_via_llm(
    question: str,
    candidate_tables: list[str],
    max_tables: int = 3,
) -> list[str] | None:
    """PD-2: ask the LLM to pick the actually-relevant tables out of a
    keyword-matched candidate pool.

    Returns the filtered table list, or None if the LLM call should be
    skipped (no candidates, single candidate, or any error). The caller
    falls back to the keyword-derived set in that case.

    Only worth invoking when keyword selection is ambiguous: multiple docs
    hit AND multiple candidates came back. Single-domain questions don't
    need this extra round-trip.
    """
    if not question or len(candidate_tables) <= 1:
        return None

    from data_agent.agent.llm_client import chat
    from data_agent.agent.column_selector import load_tables_columns

    catalog = load_tables_columns().get("tables", {})
    descriptions = []
    for table in candidate_tables:
        purpose = catalog.get(table, {}).get("purpose", "")
        descriptions.append(f"- {table}: {purpose}" if purpose else f"- {table}")

    prompt = (
        "你是 PostgreSQL 数据查询助手的 schema linking 模块。"
        f"用户问题：{question}\n\n"
        f"候选表（关键词粗筛命中）：\n" + "\n".join(descriptions) + "\n\n"
        f"只返回这个问题真正需要的表名（最多 {max_tables} 个），用逗号分隔，"
        "不要任何解释、不要 SQL、不要 markdown。如果某个候选表不需要就排除掉。"
    )
    try:
        response = chat([{"role": "user", "content": prompt}])
    except Exception as exc:
        print(f"[pd2] LLM table refine failed: {type(exc).__name__}: {exc}", flush=True)
        return None

    if not response:
        return None

    # Extract table-name-like tokens from the response and keep only those
    # that are in the candidate pool. Tolerant of commas / whitespace / quotes.
    mentioned = {
        token.strip().strip("`'\"").lower()
        for token in re.split(r"[,\n]", response)
        if token.strip()
    }
    refined = [t for t in candidate_tables if t.lower() in mentioned]
    if not refined:
        # LLM responded with something unparseable; don't trust it, signal fall-through.
        return None
    return refined[:max_tables]
