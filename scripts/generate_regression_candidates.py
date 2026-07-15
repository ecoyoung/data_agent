from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_agent.config import get_settings


DEFAULT_OUTPUT = ROOT / "evals" / "query_log_regression_candidates.json"
NEGATIVE_FEEDBACK = {"wrong_metric", "not_what_i_wanted", "unknown"}
TABLE_RE = re.compile(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)", re.I)
CTE_RE = re.compile(r"(?:\bWITH\b|,)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(", re.I)
SQL_REPAIR_MARKER = "# SQL repair attempt"


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql or "").strip()


def extract_tables(sql: str) -> list[str]:
    tables: list[str] = []
    cte_names = {match.group(1).lower() for match in CTE_RE.finditer(sql or "")}
    for match in TABLE_RE.finditer(sql or ""):
        table = match.group(1).split(".")[-1]
        if table.lower() in cte_names:
            continue
        if table not in tables:
            tables.append(table)
    return tables


def infer_required_terms(sql: str) -> list[str]:
    normalized = normalize_sql(sql)
    lowered = normalized.lower()
    candidates = [
        "ordered_revenue",
        "ordered_units",
        "order_items",
        "salesbyasin_orderedproductsales_amount",
        "salesbyasin_unitsordered",
        "trafficbyasin_sessions",
        "ams_spend",
        "ams_sales",
        "ams_orders",
        "dsp_cost",
        "dsp_total_sales",
        "report_date",
        "return_date",
        "country_code",
        "country",
        "NULLIF",
        "GROUP BY report_date",
        "GROUP BY 1",
        "UNION ALL",
        "LEFT JOIN",
    ]
    required: list[str] = []
    for term in candidates:
        if term.lower() in lowered and term not in required:
            required.append(term)
    return required[:12]


def infer_forbidden_terms(error: str, sql: str, feedback: str | None = None) -> list[str]:
    text = f"{error or ''}\n{sql or ''}".lower()
    forbidden: list[str] = []
    if "permission denied" in text:
        forbidden.append("permission denied")
    if "group by month" in text or "must appear in the group by" in text:
        forbidden.extend(["GROUP BY month"])
    if "round(double precision" in text or "function round(double precision" in text:
        forbidden.append("ROUND(double precision")
    if "avg(trafficbyasin_unitsessionpercentage" in text:
        forbidden.append("AVG(trafficbyasin_unitsessionpercentage")
    if feedback in NEGATIVE_FEEDBACK:
        forbidden.append("same_wrong_answer")
    return list(dict.fromkeys(forbidden))


def candidate_id(row: dict[str, Any], index: int) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", (row.get("user_text") or "query").lower()).strip("_")
    base = base[:48] or "query"
    return f"query_log_{row.get('query_id') or index}_{base}"


def build_candidate(row: dict[str, Any], index: int) -> dict[str, Any]:
    sql = row.get("sql") or ""
    feedback_values = sorted(
        {item for item in str(row.get("feedback_values") or "").split(",") if item}
    )
    source_reasons: list[str] = []
    if row.get("status") == "error":
        source_reasons.append("query_error")
    if any(feedback in NEGATIVE_FEEDBACK for feedback in feedback_values):
        source_reasons.append("negative_feedback")
    if SQL_REPAIR_MARKER.lower() in str(row.get("llm_response") or "").lower():
        source_reasons.append("sql_repair_attempt")

    return {
        "id": candidate_id(row, index),
        "source_query_id": row.get("query_id"),
        "source_reasons": source_reasons,
        "created_at": row.get("created_at"),
        "user_text": row.get("user_text") or "",
        "status": row.get("status"),
        "feedback": feedback_values,
        "error": row.get("error") or "",
        "sql": sql,
        "expected_tables": extract_tables(sql),
        "required_terms_suggestion": infer_required_terms(sql),
        "forbidden_terms_suggestion": infer_forbidden_terms(row.get("error") or "", sql, feedback_values[0] if feedback_values else None),
        "row_count": row.get("row_count"),
        "columns_json": _parse_jsonish(row.get("columns_json")),
        "selected_catalog_docs": _parse_jsonish(row.get("selected_catalog_docs")),
        "needs_human_review": True,
        "suggested_action": "人工确认后，将正确 SQL 和 required/forbidden terms 合并进正式 evals。",
    }


def _parse_jsonish(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def fetch_candidate_rows(db_path: Path, days: int | None, include_success_repairs: bool) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []

    filters = [
        "(q.status = 'error' OR f.feedback IN ({}){})".format(
            ",".join("?" for _ in NEGATIVE_FEEDBACK),
            " OR q.llm_response LIKE ?" if include_success_repairs else "",
        )
    ]
    params: list[Any] = list(NEGATIVE_FEEDBACK)
    if include_success_repairs:
        params.append(f"%{SQL_REPAIR_MARKER}%")
    if days is not None:
        filters.append("q.created_at >= datetime('now', ?)")
        params.append(f"-{days} days")

    query = f"""
        SELECT
            q.query_id,
            q.created_at,
            q.user_text,
            q.status,
            q.selected_catalog_docs,
            q.llm_response,
            q.sql,
            q.row_count,
            q.columns_json,
            q.error,
            q.duration_ms,
            GROUP_CONCAT(DISTINCT f.feedback) AS feedback_values
        FROM query_events q
        LEFT JOIN feedback_events f ON f.query_id = q.query_id
        WHERE {" AND ".join(filters)}
        GROUP BY q.query_id
        ORDER BY q.created_at DESC
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def generate_candidates(
    db_path: Path,
    days: int | None = 30,
    include_success_repairs: bool = True,
) -> list[dict[str, Any]]:
    rows = fetch_candidate_rows(db_path, days, include_success_repairs)
    return [build_candidate(row, index) for index, row in enumerate(rows, start=1)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate eval regression candidates from query logs.")
    parser.add_argument("--db", default=get_settings().query_log_db_path, help="SQLite query log path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument("--days", type=int, default=30, help="Only include queries from recent N days")
    parser.add_argument("--all-time", action="store_true", help="Ignore --days and include all history")
    parser.add_argument(
        "--no-success-repairs",
        action="store_true",
        help="Exclude successful queries that involved a SQL repair attempt",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    output = Path(args.output)
    candidates = generate_candidates(
        db_path,
        days=None if args.all_time else args.days,
        include_success_repairs=not args.no_success_repairs,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {output}")
    print(f"candidate_rows={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
