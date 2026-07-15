from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from data_agent.agent import query_examples


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "query_logs.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE query_events (
            query_id TEXT PRIMARY KEY,
            created_at TEXT,
            status TEXT,
            user_text TEXT,
            sql TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO query_events VALUES (?, ?, ?, ?, ?)",
        [
            ("q1", "2026-07-08", "success",
             "2026年6月广告花费最多的5个asin，以及他们的Business Report销售额",
             "SELECT advertised_asin FROM intermediate_amazon_ams_advertised_product_innerbrightness_view"),
            ("q2", "2026-07-08", "success",
             "上周 SP 广告 ACoS 排名",
             "SELECT campaign_name, SUM(ams_spend)/NULLIF(SUM(ams_sales),0) FROM intermediate_amazon_ams_campaigns_innerbrightness_view"),
            ("q3", "2026-07-08", "error",
             "广告花费",
             "SELECT malformed"),
            ("q4", "2026-07-08", "success",
             "库存库龄分析",
             "SELECT asin FROM intermediate_amazon_fba_inventory_days_blueland_view"),
        ],
    )
    conn.commit()
    conn.close()

    # Reset lru_cache so the new DB is picked up.
    query_examples._cached_success_rows.cache_clear()
    monkeypatch.setattr(query_examples, "_db_path", lambda: path)
    query_examples._cached_success_rows.cache_clear()
    return path


def test_finds_similar_ad_spend_query(db_path: Path) -> None:
    results = query_examples.find_similar_success_queries(
        "2026年7月广告花费最多的ASIN", limit=2
    )
    assert results
    assert "advertised_asin" in results[0]["sql"]


def test_does_not_return_error_rows(db_path: Path) -> None:
    results = query_examples.find_similar_success_queries("广告花费", limit=5)
    assert all("malformed" not in r["sql"] for r in results)


def test_returns_empty_when_nothing_similar(db_path: Path) -> None:
    results = query_examples.find_similar_success_queries(
        "completely unrelated xyzabc question", limit=2
    )
    # Min-score filter should drop unrelated rows.
    assert results == []


def test_handles_missing_db(tmp_path: Path, monkeypatch) -> None:
    query_examples._cached_success_rows.cache_clear()
    monkeypatch.setattr(query_examples, "_db_path", lambda: tmp_path / "missing.sqlite3")
    query_examples._cached_success_rows.cache_clear()
    assert query_examples.find_similar_success_queries("anything") == []


def test_limit_is_respected(db_path: Path) -> None:
    results = query_examples.find_similar_success_queries("广告 asin", limit=1)
    assert len(results) <= 1
