"""Profile low-cardinality field values for intermediate_amazon_* objects.

The output is a catalog aid, not a full data export. It enumerates structural
patterns for every intermediate table, then samples only low-cardinality
dimension fields. High-cardinality business keys such as ASIN, SKU, ids,
names, search terms, and targeting text are deliberately excluded.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_agent.agent.sql_executor import get_connection
from scripts.build_intermediate_catalog import fetch_catalog_rows, infer_family
from scripts.profile_intermediate_data import table_scope_token


OUTPUT_JSON = ROOT / "docs" / "intermediate_amazon_field_values.json"
OUTPUT_MD = ROOT / "docs" / "intermediate_amazon_field_values.md"

DEFAULT_TABLE_LIMIT = 462
DEFAULT_SAMPLE_ROWS = 5_000
DEFAULT_TOP_VALUES = 20
DEFAULT_MAX_DISTINCT_IN_SAMPLE = 50
DEFAULT_STATEMENT_TIMEOUT_MS = 1_200
DEFAULT_ENUM_TABLES_PER_DOMAIN = 2
MAX_ENUM_COLUMNS_PER_TABLE = 8
PREFERRED_ENUM_SCOPES = (
    "innerbrightness",
    "brumate",
    "blueland",
    "belliwelli",
    "lider_us",
    "beekeeper_us",
    "supergut",
    "perfectbar",
)

DATE_LIKE_NAMES = {
    "date",
    "report_date",
    "return_date",
    "snapshot_date",
    "purchase_date",
    "shipment_date",
    "order_date",
}
ALWAYS_ENUMERATE = {
    "ad_type",
    "ads_type",
    "ams_type",
    "brand",
    "campaign_type",
    "country",
    "country_code",
    "currency",
    "customer",
    "customer_name",
    "disposition",
    "fulfillment_channel",
    "marketplace",
    "marketplace_name",
    "match_type",
    "model",
    "order_status",
    "placement",
    "profile_country_code",
    "profile_marketplace",
    "profile_type",
    "reason",
    "report_type",
    "return_status",
    "sales_channel",
    "status",
    "targeting_type",
    "type",
    "vcc",
}
HIGH_CARDINALITY_PATTERNS = (
    "asin",
    "sku",
    "fnsku",
    "msku",
    "upc",
    "ean",
    "isbn",
    "keyword",
    "search_term",
    "searchterm",
    "targeting_expression",
    "targeting_text",
    "matched_target",
    "query",
    "title",
    "description",
    "url",
    "image",
    "email",
    "phone",
    "address",
)
HIGH_CARDINALITY_SUFFIXES = (
    "_id",
    "_ids",
    "_name",
    "_names",
    "_number",
    "_numbers",
    "_code",
    "_text",
)
HIGH_CARDINALITY_EXACT = {
    "id",
    "name",
    "campaign",
    "campaign_id",
    "campaign_name",
    "ad_group",
    "ad_group_id",
    "ad_group_name",
    "line_item",
    "line_item_id",
    "line_item_name",
    "lineitem",
    "lineitem_id",
    "lineitem_name",
    "creative",
    "creative_id",
    "creative_name",
    "order_id",
    "order_name",
    "order_number",
    "product",
    "product_name",
    "portfolio",
    "portfolio_id",
    "portfolio_name",
    "profile_id",
    "profile_name",
    "targeting",
    "targeting_id",
}
SAFE_CODE_COLUMNS = {
    "country_code",
    "currency_code",
    "marketplace_code",
    "profile_country_code",
}
ENUM_NAME_HINTS = (
    "type",
    "status",
    "state",
    "country",
    "market",
    "currency",
    "brand",
    "customer",
    "channel",
    "placement",
    "match",
    "reason",
    "category",
    "class",
    "model",
    "vcc",
    "program",
    "segment",
    "strategy",
    "tactic",
)


def json_default(value: Any) -> str | int | float | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value) if value is not None else None


def quote_table(table_name: str) -> sql.Identifier:
    return sql.Identifier("public", table_name)


def normalize_type(data_type: str) -> str:
    return data_type.lower()


def is_enum_data_type(data_type: str) -> bool:
    text = normalize_type(data_type)
    return any(token in text for token in ("text", "character", "varchar", "char", "boolean"))


def is_high_cardinality_name(column_name: str) -> bool:
    name = column_name.lower()
    if name in ALWAYS_ENUMERATE or name in SAFE_CODE_COLUMNS:
        return False
    if name in HIGH_CARDINALITY_EXACT:
        return True
    if any(pattern in name for pattern in HIGH_CARDINALITY_PATTERNS):
        return True
    if any(name.endswith(suffix) for suffix in HIGH_CARDINALITY_SUFFIXES):
        return True
    return False


def should_enumerate_column(column_name: str, data_type: str) -> tuple[bool, str]:
    name = column_name.lower()
    if name in DATE_LIKE_NAMES or name.endswith("_date") or name.endswith("_time"):
        return False, "date/time field"
    if is_high_cardinality_name(name):
        return False, "high-cardinality business key"
    if name in ALWAYS_ENUMERATE or name in SAFE_CODE_COLUMNS:
        return True, "allowlisted categorical field"
    if not is_enum_data_type(data_type):
        return False, "non-categorical data type"
    if any(hint in name for hint in ENUM_NAME_HINTS):
        return True, "categorical name hint"
    return False, "no categorical hint"


def column_order_score(column_name: str) -> tuple[int, str]:
    name = column_name.lower()
    if name in ALWAYS_ENUMERATE:
        return (0, name)
    if name in SAFE_CODE_COLUMNS:
        return (1, name)
    if any(hint in name for hint in ("type", "status", "country", "brand", "customer")):
        return (2, name)
    return (3, name)


def fetch_enum_values(
    conn,
    table: str,
    column: str,
    sample_rows: int,
    top_values: int,
    max_distinct: int,
) -> dict[str, Any]:
    query = sql.SQL(
        """
        WITH sampled AS (
            SELECT {column}::text AS value
            FROM {table}
            WHERE {column} IS NOT NULL
              AND NULLIF({column}::text, '') IS NOT NULL
            LIMIT {sample_rows}
        ),
        grouped AS (
            SELECT value, COUNT(*)::bigint AS rows
            FROM sampled
            GROUP BY value
        )
        SELECT value, rows
        FROM grouped
        ORDER BY rows DESC, value
        LIMIT {limit}
        """
    ).format(
        column=sql.Identifier(column),
        table=quote_table(table),
        sample_rows=sql.Literal(sample_rows),
        limit=sql.Literal(max_distinct + 1),
    )
    with conn.cursor() as cur:
        cur.execute(query)
        rows = [dict(row) for row in cur.fetchall()]

    distinct_in_sample = len(rows)
    if distinct_in_sample > max_distinct:
        return {
            "status": "skipped_high_distinct",
            "distinct_in_sample": distinct_in_sample,
            "values": [],
        }
    return {
        "status": "ok",
        "distinct_in_sample": distinct_in_sample,
        "values": rows[:top_values],
    }


def build_structure_profile(
    tables: list[dict[str, Any]],
    columns_by_table: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    domain_tables: dict[str, list[str]] = defaultdict(list)
    domain_column_tables: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    domain_column_types: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    scope_domain_columns: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    column_counter: Counter[str] = Counter()

    for table in tables:
        name = table["table_name"]
        domain = infer_family(name)[0]
        scope = table_scope_token(name, domain)
        domain_tables[domain].append(name)
        for column in columns_by_table.get(name, []):
            column_name = column["column_name"]
            data_type = column["data_type"]
            domain_column_tables[domain][column_name].add(name)
            domain_column_types[domain][column_name][data_type] += 1
            scope_domain_columns[f"{domain}:{scope}"][column_name].add(name)
            column_counter[column_name] += 1

    domains: dict[str, Any] = {}
    for domain, table_names in sorted(domain_tables.items()):
        table_count = len(table_names)
        column_rows = domain_column_tables[domain]
        common = [
            {
                "column": column,
                "table_count": len(seen_tables),
                "coverage": round(len(seen_tables) / table_count, 4),
                "types": dict(domain_column_types[domain][column].most_common()),
            }
            for column, seen_tables in column_rows.items()
            if len(seen_tables) == table_count
        ]
        majority = [
            {
                "column": column,
                "table_count": len(seen_tables),
                "coverage": round(len(seen_tables) / table_count, 4),
                "types": dict(domain_column_types[domain][column].most_common()),
            }
            for column, seen_tables in column_rows.items()
            if len(seen_tables) < table_count and len(seen_tables) / table_count >= 0.7
        ]
        variant = [
            {
                "column": column,
                "table_count": len(seen_tables),
                "coverage": round(len(seen_tables) / table_count, 4),
                "types": dict(domain_column_types[domain][column].most_common()),
            }
            for column, seen_tables in column_rows.items()
            if len(seen_tables) / table_count < 0.7
        ]
        domains[domain] = {
            "table_count": table_count,
            "common_columns": sorted(common, key=lambda row: row["column"]),
            "majority_columns": sorted(majority, key=lambda row: (-row["coverage"], row["column"])),
            "variant_columns": sorted(variant, key=lambda row: (-row["table_count"], row["column"]))[:80],
        }

    domain_names_by_column: dict[str, set[str]] = defaultdict(set)
    for domain, columns in domain_column_tables.items():
        for column in columns:
            domain_names_by_column[column].add(domain)

    global_common = [
        {
            "column": column,
            "table_count": count,
            "domain_count": len(domain_names_by_column[column]),
            "domains": sorted(domain_names_by_column[column]),
        }
        for column, count in column_counter.most_common()
        if len(domain_names_by_column[column]) >= 3
    ]

    scope_specific: list[dict[str, Any]] = []
    for key, columns in scope_domain_columns.items():
        domain, scope = key.split(":", 1)
        domain_columns = domain_column_tables[domain]
        specific_columns = [
            column
            for column in columns
            if len(domain_columns[column]) <= max(2, int(len(domain_tables[domain]) * 0.1))
        ]
        if specific_columns:
            scope_specific.append(
                {
                    "domain": domain,
                    "scope": scope,
                    "columns": sorted(specific_columns)[:40],
                }
            )

    return {
        "global_common_columns": global_common[:120],
        "domains": domains,
        "scope_specific_columns": sorted(
            scope_specific,
            key=lambda row: (row["domain"], row["scope"]),
        )[:300],
    }


def select_enum_tables(
    tables: list[dict[str, Any]],
    per_domain: int,
    include_domains: set[str] | None,
    skip_domains: set[str],
) -> list[dict[str, Any]]:
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for table in tables:
        domain = infer_family(table["table_name"])[0]
        if include_domains is not None and domain not in include_domains:
            continue
        if domain in skip_domains:
            continue
        by_domain[domain].append(table)

    selected: list[dict[str, Any]] = []
    for domain, domain_tables in sorted(by_domain.items()):
        def score(table: dict[str, Any]) -> tuple[int, str]:
            scope = table_scope_token(table["table_name"], domain)
            try:
                priority = PREFERRED_ENUM_SCOPES.index(scope)
            except ValueError:
                priority = len(PREFERRED_ENUM_SCOPES)
            return (priority, table["table_name"])

        selected.extend(sorted(domain_tables, key=score)[:per_domain])
    return selected


def profile_field_values(args: argparse.Namespace) -> dict[str, Any]:
    tables, columns_by_table = fetch_catalog_rows()
    selectable = [table for table in tables if table.get("can_select")][: args.table_limit]
    include_domains = parse_domain_set(args.include_domains)
    skip_domains = parse_domain_set(args.skip_domains) or set()
    enum_tables = select_enum_tables(
        selectable,
        args.enum_tables_per_domain,
        include_domains,
        skip_domains,
    )
    structure = build_structure_profile(selectable, columns_by_table)

    conn = get_connection()
    enum_results: list[dict[str, Any]] = []
    skipped_reasons: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    enum_column_counts: Counter[str] = Counter()

    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET statement_timeout = {}").format(
                    sql.Literal(args.statement_timeout_ms)
                )
            )

        for table in enum_tables:
            table_name = table["table_name"]
            domain = infer_family(table_name)[0]
            scope = table_scope_token(table_name, domain)
            candidates: list[dict[str, Any]] = []
            for column in columns_by_table.get(table_name, []):
                should_enum, reason = should_enumerate_column(
                    column["column_name"],
                    column["data_type"],
                )
                if should_enum:
                    candidates.append(column)
                else:
                    skipped_reasons[reason] += 1

            candidates = sorted(
                candidates,
                key=lambda row: column_order_score(row["column_name"]),
            )[:MAX_ENUM_COLUMNS_PER_TABLE]

            for column in candidates:
                column_name = column["column_name"]
                if args.verbose:
                    print(
                        f"enumerating {domain} {scope} {table_name}.{column_name}",
                        flush=True,
                    )
                try:
                    enum = fetch_enum_values(
                        conn,
                        table_name,
                        column_name,
                        args.sample_rows,
                        args.top_values,
                        args.max_distinct_in_sample,
                    )
                except psycopg.errors.QueryCanceled:
                    enum = {"status": "timeout", "distinct_in_sample": None, "values": []}
                except psycopg.Error as exc:
                    enum = {
                        "status": "error",
                        "error": exc.__class__.__name__,
                        "distinct_in_sample": None,
                        "values": [],
                    }

                if enum["status"] == "ok" and not enum["values"]:
                    enum["status"] = "no_values"

                enum_results.append(
                    {
                        "table": table_name,
                        "domain": domain,
                        "scope": scope,
                        "column": column_name,
                        "data_type": column["data_type"],
                        **enum,
                    }
                )
                domain_counts[domain] += 1
                enum_column_counts[column_name] += 1
    finally:
        conn.close()

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": "public.intermediate_amazon_% PostgreSQL objects",
        "table_count": len(selectable),
        "enumerated_table_count": len(enum_tables),
        "enum_policy": {
            "sample_rows_per_table_column": args.sample_rows,
            "top_values": args.top_values,
            "max_distinct_in_sample": args.max_distinct_in_sample,
            "statement_timeout_ms": args.statement_timeout_ms,
            "enum_tables_per_domain": args.enum_tables_per_domain,
            "include_domains": sorted(include_domains) if include_domains else [],
            "skip_domains": sorted(skip_domains),
            "preferred_enum_scopes": list(PREFERRED_ENUM_SCOPES),
            "excluded_high_cardinality_patterns": list(HIGH_CARDINALITY_PATTERNS),
            "excluded_high_cardinality_suffixes": list(HIGH_CARDINALITY_SUFFIXES),
            "always_enumerate": sorted(ALWAYS_ENUMERATE),
        },
        "structure": structure,
        "enum_summary": {
            "attempted_table_columns": len(enum_results),
            "by_status": dict(Counter(row["status"] for row in enum_results).most_common()),
            "by_domain": dict(domain_counts.most_common()),
            "by_column": dict(enum_column_counts.most_common(80)),
            "skipped_candidate_reasons": dict(skipped_reasons.most_common()),
        },
        "field_values": enum_results,
    }


def markdown_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def compact_values(values: list[dict[str, Any]], max_items: int = 8) -> str:
    parts = []
    for row in values[:max_items]:
        parts.append(f"{markdown_escape(row['value'])} ({row['rows']})")
    return "; ".join(parts)


def render_markdown(profile: dict[str, Any]) -> str:
    lines = [
        "# intermediate_amazon_ Field Values Profile",
        "",
        f"Generated at: `{profile['generated_at']}`",
        f"Tables analyzed: `{profile['table_count']}`",
        f"Tables sampled for values: `{profile['enumerated_table_count']}`",
        "",
        "## Scope",
        "",
        "- Structure coverage includes all selectable `intermediate_amazon_` objects.",
        "- Value enumeration samples only low-cardinality categorical fields.",
        "- ASIN, SKU, ids, names, search terms, targeting text, URLs and other high-cardinality business keys are excluded.",
        "",
        "## Main Table Types",
        "",
        "| Domain | Tables | Common columns | Majority columns | Variant columns shown |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]

    domains = profile["structure"]["domains"]
    for domain, data in sorted(domains.items()):
        lines.append(
            f"| `{domain}` | {data['table_count']} | {len(data['common_columns'])} | "
            f"{len(data['majority_columns'])} | {len(data['variant_columns'])} |"
        )

    lines.extend(
        [
            "",
            "## Global Common Fields",
            "",
            "| Column | Tables | Domains |",
            "| --- | ---: | --- |",
        ]
    )
    for row in profile["structure"]["global_common_columns"][:60]:
        lines.append(
            f"| `{markdown_escape(row['column'])}` | {row['table_count']} | "
            f"{', '.join(f'`{d}`' for d in row['domains'][:8])} |"
        )

    lines.extend(["", "## Common Fields By Domain", ""])
    for domain, data in sorted(domains.items()):
        common = ", ".join(f"`{row['column']}`" for row in data["common_columns"][:24])
        majority = ", ".join(
            f"`{row['column']}`({int(row['coverage'] * 100)}%)"
            for row in data["majority_columns"][:16]
        )
        lines.extend(
            [
                f"### `{domain}`",
                "",
                f"- Common: {common or '-'}",
                f"- Majority: {majority or '-'}",
                "",
            ]
        )

    lines.extend(
        [
            "## Scope-Specific / Variant Fields",
            "",
            "These are fields that appear in only a small minority of tables within the same domain. They are candidates for brand/store-specific handling, not necessarily guaranteed unique business semantics.",
            "",
            "| Domain | Scope | Fields |",
            "| --- | --- | --- |",
        ]
    )
    for row in profile["structure"]["scope_specific_columns"][:120]:
        fields = ", ".join(f"`{markdown_escape(column)}`" for column in row["columns"][:20])
        lines.append(f"| `{row['domain']}` | `{markdown_escape(row['scope'])}` | {fields} |")

    lines.extend(
        [
            "",
            "## Enumerated Field Values",
            "",
            "| Domain | Scope | Table | Column | Status | Values from sample |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    ok_rows = [row for row in profile["field_values"] if row["status"] == "ok"]
    non_empty = [row for row in ok_rows if row.get("values")]
    for row in non_empty[:260]:
        lines.append(
            f"| `{row['domain']}` | `{markdown_escape(row['scope'])}` | "
            f"`{markdown_escape(row['table'])}` | `{markdown_escape(row['column'])}` | "
            f"`{row['status']}` | {compact_values(row['values'])} |"
        )

    lines.extend(
        [
            "",
            "## Enumeration Summary",
            "",
            "### Status",
            "",
            "| Status | Count |",
            "| --- | ---: |",
        ]
    )
    for status, count in profile["enum_summary"]["by_status"].items():
        lines.append(f"| `{status}` | {count} |")

    lines.extend(["", "### Most Enumerated Columns", "", "| Column | Attempts |", "| --- | ---: |"])
    for column, count in list(profile["enum_summary"]["by_column"].items())[:40]:
        lines.append(f"| `{markdown_escape(column)}` | {count} |")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=OUTPUT_MD)
    parser.add_argument("--table-limit", type=int, default=DEFAULT_TABLE_LIMIT)
    parser.add_argument("--sample-rows", type=int, default=DEFAULT_SAMPLE_ROWS)
    parser.add_argument("--top-values", type=int, default=DEFAULT_TOP_VALUES)
    parser.add_argument(
        "--max-distinct-in-sample",
        type=int,
        default=DEFAULT_MAX_DISTINCT_IN_SAMPLE,
    )
    parser.add_argument(
        "--statement-timeout-ms",
        type=int,
        default=DEFAULT_STATEMENT_TIMEOUT_MS,
    )
    parser.add_argument(
        "--enum-tables-per-domain",
        type=int,
        default=DEFAULT_ENUM_TABLES_PER_DOMAIN,
        help="Number of representative tables to enumerate per domain; structure still covers all tables.",
    )
    parser.add_argument(
        "--include-domains",
        default="",
        help="Comma-separated domain allowlist for value enumeration.",
    )
    parser.add_argument(
        "--skip-domains",
        default="",
        help="Comma-separated domains to skip for value enumeration.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def parse_domain_set(value: str) -> set[str] | None:
    domains = {part.strip() for part in value.split(",") if part.strip()}
    return domains or None


def main() -> int:
    args = parse_args()
    profile = profile_field_values(args)
    args.output_json.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, default=json_default) + "\n",
        encoding="utf-8",
    )
    args.output_md.write_text(render_markdown(profile), encoding="utf-8")
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    print(json.dumps(profile["enum_summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
