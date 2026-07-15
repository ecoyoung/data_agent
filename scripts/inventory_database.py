from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import psycopg
from psycopg import sql

from data_agent.agent.sql_executor import get_connection


OUTPUT_JSON = ROOT / "docs" / "database_inventory.json"
OUTPUT_MD = ROOT / "docs" / "database_inventory.md"
METADATA_STATEMENT_TIMEOUT_MS = 120_000

TEXT_TYPE_NAMES = {"text", "varchar", "bpchar", "char"}
DATE_TYPE_NAMES = {"date", "timestamp", "timestamptz", "time", "timetz"}
SYNC_FIELD_NAMES = {"created_at", "updated_at", "parse_time_request"}
BUSINESS_DATE_NAME_RE = re.compile(r"(^|_)(date|dt|day|month)(_|$)", re.IGNORECASE)
NON_DATE_NAME_RE = re.compile(r"(_id$|_number$|cost)", re.IGNORECASE)


@dataclass(frozen=True)
class DateCandidate:
    name: str
    data_type: str
    kind: str
    category: str


def json_default(value: Any) -> str | int | float | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value) if value is not None else None


def markdown_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def quote_ident(name: str) -> sql.Identifier:
    return sql.Identifier(name)


def fetch_tables(conn: psycopg.Connection) -> list[dict[str, Any]]:
    query = """
        SELECT
            n.nspname AS schema_name,
            c.relname AS table_name,
            CASE c.relkind
                WHEN 'r' THEN 'table'
                WHEN 'p' THEN 'partitioned table'
                WHEN 'v' THEN 'view'
                WHEN 'm' THEN 'materialized view'
                WHEN 'f' THEN 'foreign table'
                ELSE c.relkind::text
            END AS object_type,
            pg_catalog.obj_description(c.oid, 'pg_class') AS table_comment,
            CASE WHEN c.reltuples >= 0 THEN c.reltuples::bigint ELSE NULL END AS estimated_rows,
            pg_catalog.has_table_privilege(c.oid, 'SELECT') AS can_select
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
          AND n.nspname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
          AND n.nspname NOT LIKE 'pg_toast%'
        ORDER BY n.nspname, c.relname;
    """
    with conn.cursor() as cur:
        cur.execute(query)
        return list(cur.fetchall())


def fetch_columns(conn: psycopg.Connection) -> dict[tuple[str, str], list[dict[str, Any]]]:
    query = """
        SELECT
            n.nspname AS schema_name,
            c.relname AS table_name,
            a.attnum AS ordinal_position,
            a.attname AS column_name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
            t.typname AS udt_name,
            CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END AS is_nullable,
            pg_catalog.pg_get_expr(d.adbin, d.adrelid) AS column_default,
            pg_catalog.col_description(c.oid, a.attnum) AS column_comment
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_type t ON t.oid = a.atttypid
        LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
          AND n.nspname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
          AND n.nspname NOT LIKE 'pg_toast%'
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY n.nspname, c.relname, a.attnum;
    """
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    with conn.cursor() as cur:
        cur.execute(query)
        for row in cur.fetchall():
            grouped.setdefault((row["schema_name"], row["table_name"]), []).append(row)
    return grouped


def is_date_type(column: dict[str, Any]) -> bool:
    data_type = str(column["data_type"]).lower()
    udt_name = str(column["udt_name"]).lower()
    return udt_name in DATE_TYPE_NAMES or data_type.startswith(("date", "timestamp", "time"))


def is_text_type(column: dict[str, Any]) -> bool:
    data_type = str(column["data_type"]).lower()
    udt_name = str(column["udt_name"]).lower()
    return udt_name in TEXT_TYPE_NAMES or data_type.startswith(("character", "text", "varchar", "char"))


def date_candidates(columns: list[dict[str, Any]]) -> list[DateCandidate]:
    candidates: list[DateCandidate] = []
    for column in columns:
        name = column["column_name"]
        lower_name = name.lower()
        data_type = column["data_type"]

        if lower_name in SYNC_FIELD_NAMES:
            if is_date_type(column):
                candidates.append(
                    DateCandidate(
                        name=name,
                        data_type=data_type,
                        kind="typed_date",
                        category="load_time",
                    )
                )
            elif is_text_type(column):
                candidates.append(
                    DateCandidate(
                        name=name,
                        data_type=data_type,
                        kind="text_date",
                        category="load_time",
                    )
                )
            continue

        if NON_DATE_NAME_RE.search(name) or not BUSINESS_DATE_NAME_RE.search(name):
            continue

        if is_date_type(column):
            candidates.append(
                DateCandidate(
                    name=name,
                    data_type=data_type,
                    kind="typed_date",
                    category="business_date",
                )
            )
        elif is_text_type(column):
            kind = "text_month" if "month" in name.lower() else "text_date"
            candidates.append(
                DateCandidate(
                    name=name,
                    data_type=data_type,
                    kind=kind,
                    category="business_date",
                )
            )
    return candidates


def max_for_candidate(
    conn: psycopg.Connection,
    schema_name: str,
    table_name: str,
    candidate: DateCandidate,
) -> dict[str, Any]:
    table_ref = sql.SQL(".").join([quote_ident(schema_name), quote_ident(table_name)])
    column_ref = quote_ident(candidate.name)

    if candidate.kind == "typed_date":
        query = sql.SQL("SELECT MAX({column})::text AS max_value FROM {table}").format(
            column=column_ref,
            table=table_ref,
        )
    elif candidate.kind == "text_month":
        query = sql.SQL(
            """
            SELECT MAX(to_date({column}, 'YYYY-MM'))::text AS max_value
            FROM {table}
            WHERE NULLIF({column}, '') ~ '^[0-9]{{4}}-[0-9]{{2}}$'
            """
        ).format(column=column_ref, table=table_ref)
    else:
        query = sql.SQL(
            """
            SELECT MAX(({column})::date)::text AS max_value
            FROM {table}
            WHERE NULLIF({column}, '') ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
            """
        ).format(column=column_ref, table=table_ref)

    try:
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()
            return {
                "column": candidate.name,
                "data_type": candidate.data_type,
                "kind": candidate.kind,
                "category": candidate.category,
                "latest": row["max_value"] if row else None,
                "error": None,
            }
    except psycopg.Error as exc:
        return {
            "column": candidate.name,
            "data_type": candidate.data_type,
            "kind": candidate.kind,
            "category": candidate.category,
            "latest": None,
            "error": str(exc).splitlines()[0],
        }


def collect_inventory() -> dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SET statement_timeout = {}").format(sql.Literal(METADATA_STATEMENT_TIMEOUT_MS)))
        tables = fetch_tables(conn)
        columns_by_table = fetch_columns(conn)

        inventory_tables: list[dict[str, Any]] = []
        for table in tables:
            key = (table["schema_name"], table["table_name"])
            columns = columns_by_table.get(key, [])
            nested_columns = [
                {
                    key: value
                    for key, value in column.items()
                    if key not in {"schema_name", "table_name"}
                }
                for column in columns
            ]
            candidates = date_candidates(columns)
            latest_dates: list[dict[str, Any]] = []
            if table["can_select"]:
                for candidate in candidates:
                    latest_dates.append(
                        max_for_candidate(
                            conn,
                            table["schema_name"],
                            table["table_name"],
                            candidate,
                        )
                    )

            inventory_tables.append(
                {
                    **table,
                    "columns": nested_columns,
                    "date_candidates": [
                        {
                            "column": candidate.name,
                            "data_type": candidate.data_type,
                            "kind": candidate.kind,
                            "category": candidate.category,
                        }
                        for candidate in candidates
                    ],
                    "latest_dates": latest_dates,
                }
            )

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "table_count": len(inventory_tables),
            "selectable_table_count": sum(1 for table in inventory_tables if table["can_select"]),
            "non_selectable_table_count": sum(1 for table in inventory_tables if not table["can_select"]),
            "tables": inventory_tables,
        }
    finally:
        conn.close()


def latest_by_category(table: dict[str, Any], category: str) -> str:
    values = [
        item["latest"]
        for item in table["latest_dates"]
        if item.get("category") == category and item.get("latest") and not item.get("error")
    ]
    return max(values) if values else ""


def render_markdown(inventory: dict[str, Any]) -> str:
    tables = inventory["tables"]
    no_select = [table for table in tables if not table["can_select"]]

    lines = [
        "# Database Inventory",
        "",
        f"Generated at: `{inventory['generated_at']}`",
        "",
        "## Summary",
        "",
        f"- Total visible objects: {inventory['table_count']}",
        f"- SELECT allowed: {inventory['selectable_table_count']}",
        f"- SELECT missing: {inventory['non_selectable_table_count']}",
        "",
        "## Permission Gaps",
        "",
    ]

    if no_select:
        lines.extend(["| Schema | Table | Type | Estimated Rows |", "| --- | --- | --- | --- |"])
        for table in no_select:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_escape(table["schema_name"]),
                        markdown_escape(table["table_name"]),
                        markdown_escape(table["object_type"]),
                        markdown_escape(table["estimated_rows"]),
                    ]
                )
                + " |"
            )
    else:
        lines.append("No visible tables are missing SELECT permission.")

    lines.extend(
        [
            "",
            "## Visible Objects",
            "",
            "| Schema | Table | Type | SELECT | Estimated Rows | Latest Business Date | Latest Load Time | Date Fields Checked |",
            "| --- | --- | --- | --- | ---: | --- | --- | --- |",
        ]
    )

    for table in tables:
        checked = ", ".join(
            f"{item['column']}[{item.get('category', 'date')}]={item['latest'] or item.get('error') or 'n/a'}"
            for item in table["latest_dates"]
        )
        if not checked and table["date_candidates"]:
            checked = ", ".join(item["column"] for item in table["date_candidates"])
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(table["schema_name"]),
                    markdown_escape(table["table_name"]),
                    markdown_escape(table["object_type"]),
                    "yes" if table["can_select"] else "no",
                    markdown_escape(table["estimated_rows"]),
                    markdown_escape(latest_by_category(table, "business_date")),
                    markdown_escape(latest_by_category(table, "load_time")),
                    markdown_escape(checked),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Columns", ""])
    for table in tables:
        lines.extend(
            [
                f"### `{table['schema_name']}.{table['table_name']}`",
                "",
                f"- Type: `{table['object_type']}`",
                f"- SELECT: `{'yes' if table['can_select'] else 'no'}`",
                f"- Estimated rows: `{table['estimated_rows']}`",
                f"- Latest business date: `{latest_by_category(table, 'business_date') or 'n/a'}`",
                f"- Latest load time: `{latest_by_category(table, 'load_time') or 'n/a'}`",
                "",
                "| # | Column | Type | Nullable | Comment |",
                "| ---: | --- | --- | --- | --- |",
            ]
        )
        for column in table["columns"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_escape(column["ordinal_position"]),
                        f"`{markdown_escape(column['column_name'])}`",
                        markdown_escape(column["data_type"]),
                        markdown_escape(column["is_nullable"]),
                        markdown_escape(column["column_comment"]),
                    ]
                )
                + " |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    inventory = collect_inventory()
    OUTPUT_JSON.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    OUTPUT_MD.write_text(render_markdown(inventory), encoding="utf-8")

    print(f"wrote {OUTPUT_JSON}")
    print(f"wrote {OUTPUT_MD}")
    print(
        "visible={visible} selectable={selectable} missing_select={missing}".format(
            visible=inventory["table_count"],
            selectable=inventory["selectable_table_count"],
            missing=inventory["non_selectable_table_count"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
