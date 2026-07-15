"""Refresh indexed_columns + latest_business_date in tables_metadata.json.

Why: those two fields drift over time. Indexes get added by DBA, business
data flows in daily, but the JSON is hand-edited. This script reads the
current state from PostgreSQL and writes just those two fields back,
preserving all other hand-curated content (keywords, use_when, avoid_when,
domain, ...).

Run:
    .venv/bin/python scripts/refresh_catalog_metadata.py
    .venv/bin/python scripts/refresh_catalog_metadata.py --dry-run

Recommended cadence: daily via cron. Pair with a weekly review of the diff.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import psycopg

from data_agent.agent.sql_executor import get_connection

METADATA_PATH = SRC / "data_agent" / "data_catalog" / "tables_metadata.json"


def _index_columns(conn: psycopg.Connection, table: str) -> list[list[str]]:
    """Return non-PK indexed column groups for `table`.

    Each entry is the column list of one index (composite indexes become a
    multi-element list). Primary-key indexes are excluded.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.indexname, i.indexdef
            FROM pg_indexes i
            WHERE i.tablename = %s
              AND i.schemaname = 'public'
            """,
            (table,),
        )
        rows = cur.fetchall()

    groups: list[list[str]] = []
    for row in rows:
        # Row is a dict (psycopg dict_row factory). Fall back to tuple access
        # in case the connection's row factory differs.
        if isinstance(row, dict):
            indexdef = row.get("indexdef") or ""
        else:
            indexdef = row[1] if len(row) > 1 else ""
        # Skip primary-key indexes; we only surface business indexes to the LLM.
        if "PRIMARY KEY" in indexdef.upper():
            continue
        cols = _extract_index_columns(indexdef)
        if cols:
            groups.append(cols)
    return groups


def _extract_index_columns(indexdef: str) -> list[str]:
    """Parse the column list out of `CREATE INDEX ... ON table (col1, col2) ...`."""
    match = re.search(r"\(([^)]+)\)", indexdef)
    if not match:
        return []
    raw = match.group(1)
    cols = [part.strip().strip('"').lower() for part in raw.split(",")]
    return [c for c in cols if c]


def _latest_business_date(
    conn: psycopg.Connection, table: str, date_field: str
) -> str | None:
    """MAX(date_field) as ISO date string.

    Tolerates three column shapes seen in the catalog:
    - real date / timestamp: ``MAX(col)::text``
    - text 'YYYY-MM-DD' (ads tables): ``MAX(col::date)::text``
    - text 'YYYY-MM' (replenishment report_month): ``MAX(to_date(col, 'YYYY-MM'))::text``
    """
    if not date_field:
        return None

    queries = [
        f"SELECT MAX(({date_field})::date)::text FROM {table}",
        f"SELECT MAX(to_date({date_field}, 'YYYY-MM-DD'))::text FROM {table} WHERE NULLIF({date_field}, '') IS NOT NULL",
        f"SELECT MAX(to_date({date_field}, 'YYYY-MM'))::text FROM {table} WHERE NULLIF({date_field}, '') ~ '^[0-9]{{4}}-[0-9]{{2}}$'",
    ]

    for query in queries:
        try:
            with conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                if not row:
                    continue
                value = next(iter(row.values())) if isinstance(row, dict) else row[0]
                if value is not None:
                    return str(value)
        except psycopg.Error:
            continue
    return None


def refresh(dry_run: bool = False) -> int:
    if not METADATA_PATH.exists():
        print(f"metadata file not found: {METADATA_PATH}", file=sys.stderr)
        return 1

    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    tables = metadata.get("tables", [])

    conn = get_connection()
    changes: list[tuple[str, str, Any, Any]] = []
    try:
        for table in tables:
            name = table.get("table")
            if not name or table.get("select_permission") is not True:
                continue

            indexed = _index_columns(conn, name)
            old_indexed = table.get("indexed_columns")
            if indexed != old_indexed:
                changes.append((name, "indexed_columns", old_indexed, indexed))
                table["indexed_columns"] = indexed

            date_field = table.get("date_field")
            if date_field:
                latest = _latest_business_date(conn, name, date_field)
                old_latest = table.get("latest_business_date")
                if latest and latest != old_latest:
                    changes.append((name, "latest_business_date", old_latest, latest))
                    table["latest_business_date"] = latest
    finally:
        conn.close()

    if not changes:
        print("no changes; metadata already up to date.")
        return 0

    print(f"{len(changes)} field update(s):")
    for name, field, old, new in changes:
        old_repr = "—" if old is None else repr(old)
        print(f"  {name}.{field}: {old_repr} -> {repr(new)}")

    if dry_run:
        print("--dry-run set; not writing.")
        return 0

    METADATA_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {METADATA_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show diffs without writing")
    args = parser.parse_args()
    return refresh(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
