"""Aggregate query_logs.sqlite3 into a one-page operations report.

Run:
    .venv/bin/python scripts/metrics.py            # last 7 days
    .venv/bin/python scripts/metrics.py --days 30  # last 30 days
    .venv/bin/python scripts/metrics.py --all      # all time

Outputs markdown to stdout. Designed for a weekly ops review: success/error
rate, P50/P95 latency, top error reasons, and slowest queries.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from statistics import quantiles

DEFAULT_DB = Path(__file__).resolve().parent.parent / "storage" / "query_logs.sqlite3"

SUCCESS_LIKE = {"success", "clarification", "llm_clarification"}
ERROR_LIKE = {"error"}


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return values[0]
    # statistics.quantiles uses inclusive method; n=100 gives 99 cut points.
    qs = quantiles(sorted(values), n=100, method="inclusive")
    idx = max(0, min(99, int(round(percentile)) - 1))
    return int(qs[idx])


def _fetch(db_path: Path, since: datetime | None) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if since is None:
        rows = conn.execute(
            "SELECT query_id, created_at, status, user_text, error, duration_ms "
            "FROM query_events ORDER BY created_at"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT query_id, created_at, status, user_text, error, duration_ms "
            "FROM query_events WHERE created_at >= ? ORDER BY created_at",
            (since.isoformat(sep=" ", timespec="seconds"),),
        ).fetchall()
    conn.close()
    return rows


def _feedback_counts(db_path: Path, since: datetime | None) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if since is None:
        rows = conn.execute(
            "SELECT feedback, COUNT(*) AS n FROM feedback_events GROUP BY feedback"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT feedback, COUNT(*) AS n FROM feedback_events "
            "WHERE created_at >= ? GROUP BY feedback",
            (since.isoformat(sep=" ", timespec="seconds"),),
        ).fetchall()
    conn.close()
    return {row["feedback"]: row["n"] for row in rows}


def _format_report(rows: list[sqlite3.Row], feedback: dict[str, int], window_label: str) -> str:
    total = len(rows)
    if total == 0:
        return f"# 数探运营指标（{window_label}）\n\n查询记录数：0，无数据可统计。\n"

    by_status = Counter(row["status"] for row in rows)
    success = sum(n for s, n in by_status.items() if s in SUCCESS_LIKE)
    error = sum(n for s, n in by_status.items() if s in ERROR_LIKE)
    other = total - success - error
    success_rate = success / total * 100
    error_rate = error / total * 100

    durations = [int(row["duration_ms"] or 0) for row in rows if row["duration_ms"]]
    p50 = _percentile(durations, 50)
    p95 = _percentile(durations, 95)

    error_rows = [row for row in rows if row["status"] in ERROR_LIKE]
    error_reasons: Counter[str] = Counter()
    for row in error_rows:
        msg = (row["error"] or "").strip()
        # Collapse verbose DB errors to a short prefix.
        first_line = msg.split("\n", 1)[0][:120]
        error_reasons[first_line or "(no error message)"] += 1

    slowest = sorted(rows, key=lambda r: -(r["duration_ms"] or 0))[:5]

    lines: list[str] = []
    lines.append(f"# 数探运营指标（{window_label}）")
    lines.append("")
    lines.append(f"- 查询总数：**{total}**")
    lines.append(f"- 成功（含澄清）：{success}（{success_rate:.1f}%）")
    lines.append(f"- 错误：{error}（{error_rate:.1f}%）")
    if other:
        lines.append(f"- 其他状态：{other}")
    lines.append(f"- P50 耗时：{p50:,} ms　P95 耗时：{p95:,} ms")
    lines.append("")

    lines.append("## 状态分布")
    for status, n in by_status.most_common():
        lines.append(f"- `{status}`: {n}")
    lines.append("")

    if error_reasons:
        lines.append("## 错误原因 Top 5")
        for reason, n in error_reasons.most_common(5):
            lines.append(f"- ({n}) {reason}")
        lines.append("")

    if feedback:
        lines.append("## 用户反馈")
        for kind, n in sorted(feedback.items(), key=lambda kv: -kv[1]):
            lines.append(f"- `{kind}`: {n}")
        lines.append("")

    if slowest:
        lines.append("## 最慢 5 个查询")
        for row in slowest:
            ms = row["duration_ms"] or 0
            text = (row["user_text"] or "").strip().replace("\n", " ")[:60]
            lines.append(f"- {ms:>7,} ms　`{row['status']}`　{text}")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="lookback window in days (default 7)")
    parser.add_argument("--all", action="store_true", help="ignore --days, aggregate all time")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="path to query_logs.sqlite3")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 1

    if args.all:
        since = None
        window_label = "全部时间"
    else:
        since = datetime.now() - timedelta(days=args.days)
        window_label = f"最近 {args.days} 天"

    rows = _fetch(args.db, since)
    feedback = _feedback_counts(args.db, since)
    print(_format_report(rows, feedback, window_label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
