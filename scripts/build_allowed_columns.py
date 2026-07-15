"""Build allowed_columns.json: ground-truth column lists for cataloged tables.

Output schema: ``{ "<table_name>": ["col1", "col2", ...] }``, covering only
tables in tables_metadata.json with select_permission=true. Used by
sql_checker.check_column_existence to catch LLM-hallucinated columns before
the SQL hits the database.

Run:
    .venv/bin/python scripts/build_allowed_columns.py
    .venv/bin/python scripts/build_allowed_columns.py --dry-run

Recommended cadence: whenever schema changes (rare); pair with
refresh_catalog_metadata.py in the same cron job.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import psycopg

from data_agent.agent.sql_executor import get_connection

METADATA_PATH = SRC / "data_agent" / "data_catalog" / "tables_metadata.json"
OUTPUT_PATH = SRC / "data_agent" / "data_catalog" / "allowed_columns.json"


def _cataloged_tables() -> list[str]:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return [
        t["table"]
        for t in metadata.get("tables", [])
        if t.get("select_permission") is True and t.get("table")
    ]


def _fetch_columns(conn: psycopg.Connection, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [row["column_name"] if isinstance(row, dict) else row[0] for row in cur.fetchall()]


def build(dry_run: bool = False) -> int:
    tables = _cataloged_tables()
    if not tables:
        print("no cataloged tables; nothing to do.", file=sys.stderr)
        return 1

    result: dict[str, list[str]] = {}
    missing: list[str] = []
    conn = get_connection()
    try:
        for table in tables:
            cols = _fetch_columns(conn, table)
            if not cols:
                missing.append(table)
                continue
            result[table] = cols
    finally:
        conn.close()

    if missing:
        print(f"warning: no columns returned for: {missing}", file=sys.stderr)

    print(f"cataloged tables: {len(tables)}, columns resolved: {len(result)}")
    for table, cols in sorted(result.items()):
        print(f"  {table}: {len(cols)} columns")

    if dry_run:
        print("--dry-run set; not writing.")
        return 0

    payload = {"version": 1, "tables": result}
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return build(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
