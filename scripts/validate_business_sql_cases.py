from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE_FILE = ROOT / "evals" / "innerbrightness_business_questions.json"
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_agent.agent.sql_checker import validate_business_sql
from data_agent.agent.sql_executor import execute_query, validate_sql


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().lower()


def validate_case(case: dict, execute: bool = False) -> list[str]:
    errors: list[str] = []
    sql = case["expected_sql"]
    normalized = normalize_sql(sql)

    valid, error = validate_sql(sql)
    if not valid:
        errors.append(f"invalid SQL safety check: {error}")

    valid, error = validate_business_sql(sql)
    if not valid:
        errors.append(f"invalid SQL business check: {error}")

    if not re.search(r"\b(date|purchase_date|report_date|snapshot_date|return_date|report_month)\b", normalized):
        errors.append("missing recognizable date filter")

    for table in case.get("expected_tables", []):
        if table.lower() not in normalized:
            errors.append(f"missing expected table: {table}")

    for term in case.get("required_terms", []):
        if term.lower() not in normalized:
            errors.append(f"missing required term: {term}")

    for term in case.get("forbidden_terms", []):
        if term and term.lower() in normalized:
            errors.append(f"contains forbidden term: {term}")

    if execute and case.get("status") == "ready" and not errors:
        rows, _, exec_error = execute_query(sql)
        if exec_error:
            errors.append(f"execution failed: {exec_error}")
        expected_row_count = case.get("expected_row_count")
        if expected_row_count is not None and len(rows) != expected_row_count:
            errors.append(f"expected {expected_row_count} rows, got {len(rows)}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="execute ready cases against PostgreSQL")
    args = parser.parse_args()

    cases = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    failed = 0
    for case in cases:
        errors = validate_case(case, execute=args.execute)
        if errors:
            failed += 1
            print(f"FAIL {case['id']}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"PASS {case['id']} ({case['status']})")

    print(f"\n{len(cases) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
