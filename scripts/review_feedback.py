from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_agent.config import get_settings


DEFAULT_OUTPUT = ROOT / "docs" / "feedback_review.md"
ACTION_LABELS = {
    "accurate": "准确",
    "wrong_metric": "口径不对",
    "not_what_i_wanted": "没查到我想要的",
    "unknown": "未知反馈",
}
REVIEW_FEEDBACK = {"wrong_metric", "not_what_i_wanted", "unknown"}


def markdown_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def fetch_feedback(db_path: Path, days: int | None, include_accurate: bool) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []

    filters = []
    params: list[Any] = []
    if days is not None:
        filters.append("f.created_at >= datetime('now', ?)")
        params.append(f"-{days} days")
    if not include_accurate:
        filters.append("f.feedback != 'accurate'")

    where = "WHERE " + " AND ".join(filters) if filters else ""
    query = f"""
        SELECT
            f.feedback_id,
            f.created_at AS feedback_at,
            f.feedback,
            f.message_id AS feedback_message_id,
            f.open_id,
            q.query_id,
            q.created_at AS query_at,
            q.session_id,
            q.message_id AS query_message_id,
            q.chat_id,
            q.user_text,
            q.status,
            q.clarification_reason,
            q.clarification_question,
            q.selected_catalog_docs,
            q.sql,
            q.row_count,
            q.error,
            q.duration_ms
        FROM feedback_events f
        LEFT JOIN query_events q ON q.query_id = f.query_id
        {where}
        ORDER BY f.created_at DESC
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def render_report(rows: list[dict[str, Any]], db_path: Path, days: int | None, include_accurate: bool) -> str:
    title = "# Feedback Review"
    scope = "全部反馈" if include_accurate else "需复盘反馈"
    days_text = "全部时间" if days is None else f"最近 {days} 天"

    lines = [
        title,
        "",
        f"- SQLite: `{db_path}`",
        f"- 范围: {scope}，{days_text}",
        f"- 记录数: {len(rows)}",
        "",
    ]

    if not rows:
        lines.append("当前没有需要复盘的反馈。")
        lines.append("")
        return "\n".join(lines)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["feedback"]] = counts.get(row["feedback"], 0) + 1

    lines.extend(["## Summary", ""])
    for feedback, count in sorted(counts.items(), key=lambda item: item[0]):
        lines.append(f"- {ACTION_LABELS.get(feedback, feedback)}: {count}")

    lines.extend(
        [
            "",
            "## Review Queue",
            "",
            "| Feedback | Time | Question | Status | Rows | Duration | Query ID |",
            "| --- | --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_escape(ACTION_LABELS.get(row["feedback"], row["feedback"])),
                    markdown_escape(row["feedback_at"]),
                    markdown_escape(row["user_text"]),
                    markdown_escape(row["status"]),
                    markdown_escape(row["row_count"]),
                    markdown_escape(row["duration_ms"]),
                    markdown_escape(row["query_id"]),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Details", ""])
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"### {index}. {ACTION_LABELS.get(row['feedback'], row['feedback'])}",
                "",
                f"- Feedback at: `{row['feedback_at']}`",
                f"- Query ID: `{row['query_id']}`",
                f"- Query status: `{row['status']}`",
                f"- Session: `{row['session_id']}`",
                f"- Message: `{row['query_message_id']}`",
                f"- Row count: `{row['row_count']}`",
                f"- Duration ms: `{row['duration_ms']}`",
                "",
                "**User Question**",
                "",
                row.get("user_text") or "",
                "",
            ]
        )
        if row.get("selected_catalog_docs"):
            lines.extend(["**Selected Catalog Docs**", "", f"`{row['selected_catalog_docs']}`", ""])
        if row.get("clarification_question"):
            lines.extend(["**Clarification**", "", row["clarification_question"], ""])
        if row.get("error"):
            lines.extend(["**Error**", "", row["error"], ""])
        if row.get("sql"):
            lines.extend(["**SQL**", "", "```sql", row["sql"], "```", ""])
        lines.extend(
            [
                "**Suggested Follow-Up**",
                "",
                "- 判断是否需要新增或修改 eval case。",
                "- 判断是否需要补充 Data Catalog AI_HINT。",
                "- 判断是否需要新增 clarifier 或 SQL checker 规则。",
                "",
            ]
        )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export feedback review queue from SQLite logs.")
    parser.add_argument("--db", default=get_settings().query_log_db_path, help="SQLite query log path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Markdown report path")
    parser.add_argument("--days", type=int, default=None, help="Only include feedback from recent N days")
    parser.add_argument("--include-accurate", action="store_true", help="Include accurate feedback too")
    args = parser.parse_args()

    db_path = Path(args.db)
    output = Path(args.output)
    rows = fetch_feedback(db_path, args.days, args.include_accurate)
    report = render_report(rows, db_path, args.days, args.include_accurate)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")

    print(f"wrote {output}")
    print(f"feedback_rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
