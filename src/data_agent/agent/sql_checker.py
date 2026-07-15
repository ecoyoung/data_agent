from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from data_agent.data_catalog import load_catalog_rules


CATALOG_DIR = Path(__file__).resolve().parent.parent / "data_catalog"
TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)",
    re.IGNORECASE,
)
DATE_FILTER_RE = re.compile(
    r"\b(date|purchase_date|report_date|snapshot_date|return_date|shipment_date|report_month)\b"
    r".{0,80}(=|>=|>|<|<=|\bbetween\b|\bin\b)",
    re.IGNORECASE | re.DOTALL,
)
CTE_RE = re.compile(r"(?:\bWITH\b|,)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", re.IGNORECASE)
PII_PATTERNS = [
    "buyer_email",
    "buyer_name",
    "buyer_phone_number",
    "bill_address",
    "ship_address",
    "recipient_name",
    "ship_phone_number",
    "ship_postal_code",
    "tracking_number",
    "customer_comments",
]
DATE_REQUIRED_TABLE_PREFIXES = (
    "intermediate_amazon_",
    "amazon_3p_",
    "amazon_ads_sp_",
    "amazon_ads_sb_",
    "amazon_replenishment_",
)
COUNT_LIKE_DIVISION_DENOMINATORS = (
    "session",
    "click",
    "impression",
    "unit",
    "order",
    "purchase",
    "quantity",
    "view",
)
MONEY_LIKE_DIVISION_DENOMINATORS = (
    "sales",
    "revenue",
    "amount",
    "price",
    "cost",
    "spend",
)
SAFE_CASE_DIVISION_RE = re.compile(
    r"\bcase\s+when\s+(?:coalesce\s*\(\s*)?([a-z_][a-z0-9_]*)(?:\s*,\s*0\s*\))?\s*>\s*0"
    r"\s+then\s+[^;]*?/\s*(?:coalesce\s*\(\s*)?\1\b[^;]*?\s+else\s+[^;]*?\bend\b",
    re.IGNORECASE | re.DOTALL,
)
MONTH_TO_CHAR_ALIAS_RE = re.compile(
    r"\bto_char\s*\(\s*(?:[a-z_][a-z0-9_]*\.)?report_date\s*,\s*'yyyy-mm'\s*\)\s+as\s+month\b",
    re.IGNORECASE,
)
GROUP_BY_MONTH_ALIAS_RE = re.compile(
    r"\bgroup\s+by\s+month\b",
    re.IGNORECASE,
)


def normalize_sql(sql: str) -> str:
    cleaned = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    cleaned = re.sub(r"--.*?$", " ", cleaned, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


ROUND_CALL_RE = re.compile(r"\bROUND\s*\(", re.IGNORECASE)


def coerce_round_to_numeric(sql: str) -> str:
    """Auto-cast each ``ROUND(expr, n)`` first argument to numeric.

    PostgreSQL has ``ROUND(numeric, integer)`` but no ``ROUND(double precision,
    integer)``. LLMs routinely forget the cast on double-precision columns.
    Walk every ROUND( call, parse its arguments with balanced-paren / quote
    awareness, and wrap the first argument in ``(expr)::numeric`` when it does
    not already contain a numeric cast. Idempotent.
    """
    if not sql or "ROUND" not in sql.upper():
        return sql

    matches = list(ROUND_CALL_RE.finditer(sql))
    if not matches:
        return sql

    result = sql
    for match in reversed(matches):
        open_paren_pos = result.index("(", match.start())
        depth = 1
        i = open_paren_pos + 1
        in_quote = False
        while i < len(result):
            ch = result[i]
            if ch == "'":
                in_quote = not in_quote
            elif not in_quote:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
            i += 1
        if depth != 0 or i >= len(result):
            continue

        inner = result[open_paren_pos + 1 : i]
        args = split_top_level(inner, ",")
        if len(args) != 2:
            continue

        expr = args[0].strip()
        digits = args[1].strip()
        if "::numeric" in expr.lower() or "::decimal" in expr.lower():
            continue

        new_call = f"ROUND(({expr})::numeric, {digits})"
        result = result[: match.start()] + new_call + result[i + 1 :]

    return result


@lru_cache
def allowed_tables() -> set[str]:
    metadata_file = CATALOG_DIR / "tables_metadata.json"
    if not metadata_file.exists():
        return set()

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    return {
        table["table"].lower()
        for table in metadata.get("tables", [])
        if table.get("select_permission") is True
    }


@lru_cache
def allowed_columns() -> dict[str, set[str]]:
    """Ground-truth column lists per cataloged table.

    Used to catch LLM-hallucinated columns before SQL execution. Returns
    {table_name_lower: {column_names_lower}}. Empty dict when the file is
    missing — caller should treat that as "no column check possible" and skip.
    """
    path = CATALOG_DIR / "allowed_columns.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        table.lower(): {col.lower() for col in cols}
        for table, cols in data.get("tables", {}).items()
    }


# Match `<token>`, `<token>.<token>` (qualified), and quoted `"token"`.
# Used to extract column references from SELECT / WHERE / GROUP BY / ORDER BY
# / JOIN ON. Deliberately permissive: false positives get filtered by the
# allowed_columns lookup.
COLUMN_REF_RE = re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_"][a-zA-Z0-9_"]*|\b[a-zA-Z_][a-zA-Z0-9_]*\b')
SELECT_ALIAS_RE = re.compile(r"\bAS\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", re.IGNORECASE)
FROM_JOIN_ALIAS_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)"
    r"(?:\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*))?",
    re.IGNORECASE,
)


def _extract_column_refs_per_table(sql: str, tables: set[str]) -> dict[str, set[str]]:
    """For each referenced table, extract column names that appear in the SQL.

    Conservative: only flags references that are clearly columns (not function
    names, keywords, or aliases). Uses table-alias qualification when present
    to attribute columns to the right table; unqualified references are
    collected against every referenced table (the caller dedups).
    """
    # Build alias map: scan FROM/JOIN for `table [AS] alias`.
    alias_to_table: dict[str, str] = {}
    for match in FROM_JOIN_ALIAS_RE.finditer(sql):
        table_name = match.group(1).split(".")[-1].lower()
        alias = match.group(2)
        if alias:
            alias_to_table[alias.lower()] = table_name

    refs_by_table: dict[str, set[str]] = {t: set() for t in tables}
    qualified_re = re.compile(
        r'''\b([a-zA-Z_][a-zA-Z0-9_]*)\.(["a-zA-Z_]["a-zA-Z0-9_]*)'''
    )
    for match in qualified_re.finditer(sql):
        alias_or_table = match.group(1).lower()
        col = match.group(2).strip('"').lower()
        target = alias_to_table.get(alias_or_table) or (
            alias_or_table if alias_or_table in refs_by_table else None
        )
        if target and target in refs_by_table:
            refs_by_table[target].add(col)

    return refs_by_table


def _extract_unqualified_refs_for_single_table(sql: str, table: str) -> set[str]:
    """Extract bare column refs for simple single-table SQL.

    This deliberately skips CTEs and multi-table queries to avoid false
    positives. It catches common LLM hallucinations such as `country = 'US'`
    on a table that only exposes `country_code`.
    """
    if CTE_RE.search(sql):
        return set()

    without_strings = re.sub(r"'(?:''|[^'])*'", " ", sql)
    without_qualified = re.sub(
        r"\b[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*\b",
        " ",
        without_strings,
    )
    aliases = {match.group(1).lower() for match in SELECT_ALIAS_RE.finditer(without_qualified)}
    table_aliases = {
        match.group(2).lower()
        for match in FROM_JOIN_ALIAS_RE.finditer(without_qualified)
        if match.group(2)
    }
    table_parts = set(table.lower().split("_")) | {table.lower(), "public"}

    refs: set[str] = set()
    for token in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", without_qualified):
        lowered = token.lower()
        if lowered in NON_COLUMN_TOKENS:
            continue
        if lowered in aliases or lowered in table_aliases or lowered in table_parts:
            continue
        refs.add(lowered)
    return refs


# SQL keywords / function names that are NOT columns even though they match
# the column-name regex. Used to filter false positives when checking
# unqualified column references would be too noisy. (We currently only check
# qualified refs, but keep this for the future unqualified path.)
NON_COLUMN_TOKENS = frozenset(
    {
        "select", "from", "where", "group", "by", "order", "having", "limit",
        "offset", "join", "left", "right", "inner", "outer", "full", "cross",
        "on", "using", "as", "and", "or", "not", "in", "is", "null", "like",
        "between", "case", "when", "then", "else", "end", "with", "union",
        "all", "distinct", "asc", "desc", "date", "numeric", "text", "int",
        "integer", "boolean", "sum", "avg", "min", "max", "count", "round",
        "coalesce", "nullif", "greatest", "least", "cast", "to_char",
        "to_date", "to_number", "regexp_replace", "substr", "trim", "lower",
        "upper", "length", "extract", "date_trunc", "now", "current_date",
        "true", "false", "day", "month", "year", "week", "hour", "minute",
        "second", "filter",
    }
)


def check_column_existence(sql: str) -> list[str]:
    """Validate that column references resolve against the real schema.

    Returns a list of human-readable issue strings; empty list = clean.
    Skips silently when allowed_columns.json is missing (e.g. before
    build_allowed_columns.py has been run).
    """
    columns_by_table = allowed_columns()
    if not columns_by_table:
        return []

    tables = referenced_tables(sql)
    if not tables:
        return []

    refs_by_table = _extract_column_refs_per_table(sql, tables)
    if len(tables) == 1:
        table = next(iter(tables))
        refs_by_table.setdefault(table, set()).update(
            _extract_unqualified_refs_for_single_table(sql, table)
        )
    issues: list[str] = []
    for table, refs in refs_by_table.items():
        allowed = columns_by_table.get(table)
        if not allowed:
            # Table not in our allowed list (shouldn't happen — caller already
            # validated table name); skip.
            continue
        unknown = sorted(refs - allowed)
        if unknown:
            issues.append(
                f"表 {table} 引用了不存在的列：{', '.join(unknown[:5])}"
                + ("…" if len(unknown) > 5 else "")
            )
    return issues


def referenced_tables(sql: str) -> set[str]:
    tables: set[str] = set()
    cte_names = {match.group(1).lower() for match in CTE_RE.finditer(sql)}
    for match in TABLE_RE.finditer(sql):
        table = match.group(1).lower()
        table_name = table.split(".")[-1]
        if table_name not in cte_names:
            tables.add(table_name)
    return tables


def strip_qualified_column_prefixes(sql: str) -> str:
    return re.sub(r"\b[a-z_][a-z0-9_]*\.([a-z_][a-z0-9_]*)\b", r"\1", sql)


def split_top_level(text: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_single_quote = False
    for idx, char in enumerate(text):
        if char == "'":
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif char == delimiter and depth == 0:
                parts.append(text[start:idx].strip())
                start = idx + 1
    parts.append(text[start:].strip())
    return parts


def iter_function_arguments(sql: str, function_name: str) -> list[list[str]]:
    calls: list[list[str]] = []
    pattern = re.compile(rf"\b{re.escape(function_name)}\s*\(", re.IGNORECASE)
    for match in pattern.finditer(sql):
        args_start = match.end()
        depth = 1
        in_single_quote = False
        for idx in range(args_start, len(sql)):
            char = sql[idx]
            if char == "'":
                in_single_quote = not in_single_quote
            elif not in_single_quote:
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        calls.append(split_top_level(sql[args_start:idx], ","))
                        break
    return calls


def has_safe_division_guard(normalized_sql: str) -> bool:
    if "nullif" in normalized_sql:
        return True

    guard_sql = strip_qualified_column_prefixes(normalized_sql)
    return SAFE_CASE_DIVISION_RE.search(guard_sql) is not None


def round_division_type_issues(normalized_sql: str) -> list[str]:
    issues: list[str] = []
    for args in iter_function_arguments(normalized_sql, "round"):
        if len(args) < 2:
            continue

        first_arg = args[0]
        if "/" not in first_arg:
            continue
        if re.search(r"\)\s*::\s*numeric\s*$", first_arg) or re.search(r"::\s*numeric\s*$", first_arg):
            continue

        division_parts = split_top_level(first_arg, "/")
        denominators = division_parts[1:]
        if denominators and all(round_division_denominator_is_safe(denominator) for denominator in denominators):
            continue

        issues.append("ROUND(expr, 位数) 中的除法结果必须整体转为 numeric，或确保分子分母均为 numeric")
        break
    return issues


def round_division_denominator_is_safe(denominator: str) -> bool:
    if "::numeric" in denominator:
        return True
    if any(keyword in denominator for keyword in COUNT_LIKE_DIVISION_DENOMINATORS):
        return True
    if any(keyword in denominator for keyword in MONEY_LIKE_DIVISION_DENOMINATORS):
        return False
    return True


def month_alias_group_by_issues(sql: str) -> list[str]:
    if MONTH_TO_CHAR_ALIAS_RE.search(sql) and GROUP_BY_MONTH_ALIAS_RE.search(sql):
        return [
            "月度聚合使用 to_char(report_date, 'YYYY-MM') AS month 时不能 GROUP BY month；请使用 GROUP BY 1 或 GROUP BY to_char(report_date, 'YYYY-MM')"
        ]
    return []


def structured_forbidden_sql_issues(normalized_sql: str, tables: set[str]) -> list[str]:
    issues: list[str] = []
    for rule in load_catalog_rules().get("forbidden_sql", []):
        table_prefixes = tuple(str(prefix).lower() for prefix in rule.get("table_prefixes", []))
        if table_prefixes and not any(table.startswith(table_prefixes) for table in tables):
            continue

        requires = [str(item).lower() for item in rule.get("requires", [])]
        if requires and not all(item in normalized_sql for item in requires):
            continue

        patterns = [str(pattern).lower() for pattern in rule.get("patterns", [])]
        if patterns and any(pattern in normalized_sql for pattern in patterns):
            message = str(rule.get("message") or f"SQL 违反结构化规则：{rule.get('id', '')}")
            if rule.get("id") == "pii_fields":
                matched = next((pattern for pattern in patterns if pattern in normalized_sql), "")
                message = f"{message}：{matched}" if matched else message
            issues.append(message)
    return issues


def check_business_rules(sql: str) -> list[str]:
    normalized = normalize_sql(sql)
    tables = referenced_tables(normalized)
    issues: list[str] = []

    allowed = allowed_tables()
    if allowed:
        unknown_tables = sorted(table for table in tables if table not in allowed)
        if unknown_tables:
            issues.append(f"SQL 使用了 Catalog 外或无权限表：{unknown_tables[0]}")

    if any(table.startswith(DATE_REQUIRED_TABLE_PREFIXES) for table in tables):
        if not DATE_FILTER_RE.search(normalized):
            issues.append("事实表查询必须包含明确的业务日期过滤")

    issues.extend(structured_forbidden_sql_issues(normalized, tables))

    issues.extend(round_division_type_issues(normalized))
    if not any("不能 GROUP BY month" in issue for issue in issues):
        issues.extend(month_alias_group_by_issues(normalized))

    if any(table.startswith("intermediate_amazon_3p_sales_and_traffic_") for table in tables):
        if "avg(trafficbyasin_unitsessionpercentage" in normalized and not any("不能默认 AVG" in issue for issue in issues):
            issues.append("Business Report 转化率不能默认 AVG(unit session percentage)，应使用 SUM(units ordered) / SUM(sessions)")
        if "trafficbyasin_sessions" in normalized and "salesbyasin_unitsordered" in normalized:
            if "/" in normalized and not has_safe_division_guard(normalized):
                issues.append("Business Report 转化率计算必须使用 NULLIF 或 CASE WHEN 防止除零")

    return issues


def validate_business_sql(sql: str) -> tuple[bool, str]:
    issues = check_business_rules(sql)
    issues.extend(check_column_existence(sql))
    if issues:
        return False, "；".join(issues)
    return True, ""
