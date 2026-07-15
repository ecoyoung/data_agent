"""Profile intermediate_amazon_* data content for Catalog enrichment.

This is intentionally read-only. It samples business-date ranges, row counts,
and identity dimensions such as brand/customer/country/profile_name so the
Data Catalog can route multi-brand questions with facts instead of guesses.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from psycopg import sql

from data_agent.agent.sql_executor import get_connection
from scripts.build_intermediate_catalog import (
    DATE_FIELD_PRIORITY,
    infer_family,
    fetch_catalog_rows,
)


OUTPUT_JSON = ROOT / "docs" / "intermediate_amazon_profile.json"
OUTPUT_MD = ROOT / "docs" / "intermediate_amazon_profile.md"
METADATA_PATH = SRC / "data_agent" / "data_catalog" / "tables_metadata.json"
IDENTITY_FIELDS = (
    "brand",
    "customer",
    "customer_name",
    "country",
    "country_code",
    "profile_name",
    "model",
    "report_type",
    "ams_type",
    "ads_type",
    "ad_type",
    "vcc",
)
SAMPLE_LIMIT = 12
PROFILE_STATEMENT_TIMEOUT_MS = 2_000
PROFILE_TABLE_LIMIT = 90
PROBE_TABLES = {
    "intermediate_amazon_3p_orders_innerbrightness_view",
    "intermediate_amazon_3p_orders_belliwelli_view",
    "intermediate_amazon_3p_sales_and_traffic_innerbrightness_view",
    "intermediate_amazon_ams_campaigns_belliwelli_view",
    "intermediate_amazon_ams_search_term_belliwelli_view",
    "intermediate_amazon_ams_targeting_innerbrightness_view",
    "intermediate_amazon_ams_advertised_product_innerbrightness_view",
    "intermediate_amazon_fba_returns_belliwelli_view",
    "intermediate_amazon_dsp_order_funnel_belliwelli_view",
}
PRIORITY_IDENTITY_FIELDS = (
    "brand",
    "customer",
    "customer_name",
    "country_code",
    "country",
    "profile_name",
)


def json_default(value: Any) -> str | int | float | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value) if value is not None else None


def quote_table(table_name: str) -> sql.Identifier:
    return sql.Identifier("public", table_name)


def date_field(columns: list[dict[str, Any]]) -> str | None:
    names = {row["column_name"] for row in columns}
    for candidate in DATE_FIELD_PRIORITY:
        if candidate in names:
            return candidate
    return None


def is_textual_type(data_type: str) -> bool:
    lower = data_type.lower()
    return any(token in lower for token in ("text", "character", "varchar", "char"))


def table_scope_token(table_name: str, domain: str) -> str:
    base = table_name.removeprefix("intermediate_amazon_").removesuffix("_view")
    candidates = [
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
    ]
    for prefix in sorted(candidates, key=len, reverse=True):
        if base.startswith(prefix + "_"):
            return base[len(prefix) + 1 :]
    return base


def fetch_scalar(conn, query: sql.Composed | sql.SQL) -> Any:
    with conn.cursor() as cur:
        cur.execute(query)
        row = cur.fetchone()
        if not row:
            return None
        return next(iter(row.values())) if isinstance(row, dict) else row[0]


def fetch_identity_values(conn, table: str, column: str) -> list[dict[str, Any]]:
    query = sql.SQL(
        """
        SELECT DISTINCT {column}::text AS value
        FROM {table}
        WHERE {column} IS NOT NULL
          AND NULLIF({column}::text, '') IS NOT NULL
        LIMIT {limit}
        """
    ).format(
        column=sql.Identifier(column),
        table=quote_table(table),
        limit=sql.Literal(SAMPLE_LIMIT),
    )
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            return [dict(row) | {"rows": None} for row in cur.fetchall()]
    except psycopg.Error:
        return []


def fetch_date_range(conn, table: str, column: str, data_type: str) -> dict[str, Any]:
    column_ref = sql.Identifier(column)
    if is_textual_type(data_type):
        expr = sql.SQL("({column})::date").format(column=column_ref)
        predicate = sql.SQL("NULLIF({column}, '') ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'").format(
            column=column_ref
        )
    else:
        expr = sql.SQL("{column}::date").format(column=column_ref)
        predicate = sql.SQL("{column} IS NOT NULL").format(column=column_ref)
    query = sql.SQL(
        """
        SELECT MIN({expr})::text AS min_date, MAX({expr})::text AS max_date
        FROM {table}
        WHERE {predicate}
        """
    ).format(expr=expr, table=quote_table(table), predicate=predicate)
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone() or {}
            return dict(row)
    except psycopg.Error:
        return {"min_date": None, "max_date": None}


def profile_tables() -> dict[str, Any]:
    tables, columns_by_table = fetch_catalog_rows()
    conn = get_connection()
    profiles: list[dict[str, Any]] = []
    family_counter: Counter[str] = Counter()
    scope_counter: Counter[str] = Counter()
    identity_value_counter: dict[str, Counter[str]] = defaultdict(Counter)

    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET statement_timeout = {}").format(
                    sql.Literal(PROFILE_STATEMENT_TIMEOUT_MS)
                )
            )
        probed = 0
        for table in tables:
            name = table["table_name"]
            columns = columns_by_table.get(name, [])
            columns_by_name = {row["column_name"]: row for row in columns}
            domain, grain, keywords, purpose = infer_family(name)
            family_counter[domain] += 1
            scope = table_scope_token(name, domain)
            scope_counter[scope] += 1

            row_count = table.get("estimated_rows")
            should_probe = name in PROBE_TABLES and probed < PROFILE_TABLE_LIMIT

            date_col = date_field(columns)
            date_range: dict[str, Any] = {"min_date": None, "max_date": None}
            if should_probe and date_col:
                date_range = fetch_date_range(
                    conn,
                    name,
                    date_col,
                    columns_by_name[date_col]["data_type"],
                )

            identities: dict[str, list[dict[str, Any]]] = {}
            identity_fields = [
                field for field in PRIORITY_IDENTITY_FIELDS if field in columns_by_name
            ][:2]
            if should_probe:
                probed += 1
            for field in identity_fields if should_probe else []:
                if field not in columns_by_name:
                    continue
                values = fetch_identity_values(conn, name, field)
                identities[field] = values
                for value in values[:5]:
                    identity_value_counter[field][str(value["value"])] += 1

            profiles.append(
                {
                    "table": name,
                    "domain": domain,
                    "scope_token": scope,
                    "grain": grain,
                    "object_type": table["object_type"],
                    "row_count": row_count,
                    "date_field": date_col,
                    "min_business_date": date_range.get("min_date"),
                    "max_business_date": date_range.get("max_date"),
                    "identity_values": identities,
                }
            )
    finally:
        conn.close()

    return {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": "public.intermediate_amazon_% PostgreSQL objects",
        "table_count": len(profiles),
        "family_counts": dict(sorted(family_counter.items())),
        "scope_counts": dict(scope_counter.most_common()),
        "top_identity_values": {
            field: dict(counter.most_common(30))
            for field, counter in sorted(identity_value_counter.items())
        },
        "tables": profiles,
    }


def markdown_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(profile: dict[str, Any]) -> str:
    lines = [
        "# intermediate_amazon_ Data Profile",
        "",
        f"Generated at: `{profile['generated_at']}`",
        f"Tables profiled: `{profile['table_count']}`",
        "",
        "## Family Counts",
        "",
        "| Domain | Tables |",
        "| --- | ---: |",
    ]
    for domain, count in profile["family_counts"].items():
        lines.append(f"| `{domain}` | {count} |")

    lines.extend(["", "## Top Scope Tokens", "", "| Scope token | Tables |", "| --- | ---: |"])
    for scope, count in list(profile["scope_counts"].items())[:80]:
        lines.append(f"| `{markdown_escape(scope)}` | {count} |")

    lines.extend(["", "## Top Identity Values", ""])
    for field, values in profile["top_identity_values"].items():
        lines.extend([f"### `{field}`", "", "| Value | Approx rows in sampled top values |", "| --- | ---: |"])
        for value, rows in list(values.items())[:20]:
            lines.append(f"| {markdown_escape(value)} | {rows} |")
        lines.append("")

    lines.extend(
        [
            "## Table Profiles",
            "",
            "| Table | Domain | Scope | Rows | Date field | Min date | Max date | Identity fields |",
            "| --- | --- | --- | ---: | --- | --- | --- | --- |",
        ]
    )
    for table in profile["tables"]:
        identity_fields = ", ".join(
            f"{field}={'; '.join(str(v['value']) for v in values[:3])}"
            for field, values in table["identity_values"].items()
            if values
        )
        lines.append(
            "| `{table}` | `{domain}` | `{scope}` | {rows} | `{date_field}` | {min_date} | {max_date} | {identities} |".format(
                table=markdown_escape(table["table"]),
                domain=markdown_escape(table["domain"]),
                scope=markdown_escape(table["scope_token"]),
                rows=table["row_count"] or 0,
                date_field=markdown_escape(table["date_field"]),
                min_date=markdown_escape(table["min_business_date"]),
                max_date=markdown_escape(table["max_business_date"]),
                identities=markdown_escape(identity_fields),
            )
        )
    return "\n".join(lines) + "\n"


def enrich_metadata(profile: dict[str, Any]) -> None:
    if not METADATA_PATH.exists():
        return
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    by_table = {table["table"]: table for table in profile["tables"]}
    for table in metadata.get("tables", []):
        prof = by_table.get(table.get("table"))
        if not prof:
            continue
        table["row_count"] = prof.get("row_count")
        table["min_business_date"] = prof.get("min_business_date")
        table["latest_business_date"] = prof.get("max_business_date")
        table["scope_token"] = prof.get("scope_token")
        table["identity_fields"] = {
            field: [value["value"] for value in values[:5]]
            for field, values in prof.get("identity_values", {}).items()
            if values
        }
    METADATA_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    profile = profile_tables()
    OUTPUT_JSON.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, default=json_default) + "\n",
        encoding="utf-8",
    )
    OUTPUT_MD.write_text(render_markdown(profile), encoding="utf-8")
    enrich_metadata(profile)
    print(f"wrote {OUTPUT_JSON}")
    print(f"wrote {OUTPUT_MD}")
    print(f"enriched {METADATA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
