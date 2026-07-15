import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.metrics import _fetch, _format_report, _percentile


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "query_logs.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE query_events (
            query_id TEXT PRIMARY KEY,
            created_at TEXT,
            status TEXT,
            user_text TEXT,
            error TEXT,
            duration_ms INTEGER
        );
        CREATE TABLE feedback_events (
            feedback_id TEXT PRIMARY KEY,
            created_at TEXT,
            feedback TEXT
        );
        """
    )
    now = datetime.now()
    rows = []
    for i in range(10):
        rows.append(
            (
                f"q{i}",
                (now - timedelta(days=i)).isoformat(sep=" ", timespec="seconds"),
                "success" if i % 2 == 0 else "error",
                f"question {i}",
                f"err {i}" if i % 2 else "",
                1000 + i * 1000,
            )
        )
    conn.executemany(
        "INSERT INTO query_events VALUES (?, ?, ?, ?, ?, ?)", rows
    )
    conn.executemany(
        "INSERT INTO feedback_events VALUES (?, ?, ?)",
        [
            ("f1", now.isoformat(sep=" ", timespec="seconds"), "accurate"),
            ("f2", now.isoformat(sep=" ", timespec="seconds"), "wrong_metric"),
        ],
    )
    conn.commit()
    conn.close()
    return path


def test_percentile_handles_small_lists() -> None:
    assert _percentile([], 50) == 0
    assert _percentile([42], 50) == 42


def test_percentile_orders_values() -> None:
    values = list(range(1, 101))
    p50 = _percentile(values, 50)
    p95 = _percentile(values, 95)
    assert 45 <= p50 <= 55
    assert p95 >= 90


def test_fetch_returns_all_rows_when_since_none(db_path: Path) -> None:
    rows = _fetch(db_path, None)
    assert len(rows) == 10


def test_fetch_filters_by_since(db_path: Path) -> None:
    since = datetime.now() - timedelta(days=3)
    rows = _fetch(db_path, since)
    assert 2 <= len(rows) <= 5


def test_format_report_contains_key_sections(db_path: Path) -> None:
    rows = _fetch(db_path, None)
    report = _format_report(rows, {"accurate": 1, "wrong_metric": 1}, "test window")
    assert "查询总数：**10**" in report
    assert "成功（含澄清）" in report
    assert "## 状态分布" in report
    assert "## 错误原因 Top 5" in report
    assert "## 用户反馈" in report
    assert "## 最慢 5 个查询" in report


def test_format_report_handles_empty() -> None:
    report = _format_report([], {}, "empty")
    assert "查询记录数：0" in report
