import sqlite3

from scripts.generate_regression_candidates import (
    build_candidate,
    extract_tables,
    generate_candidates,
    infer_forbidden_terms,
    infer_required_terms,
)


def test_extract_tables_from_sql() -> None:
    sql = """
    WITH sales AS (
        SELECT * FROM intermediate_amazon_3p_orders_brumate_view
    )
    SELECT *
    FROM sales
    LEFT JOIN intermediate_amazon_ams_campaigns_brumate_view a ON true
    """

    assert extract_tables(sql) == [
        "intermediate_amazon_3p_orders_brumate_view",
        "intermediate_amazon_ams_campaigns_brumate_view",
    ]


def test_term_inference_from_sql_and_error() -> None:
    sql = "SELECT report_date, SUM(ordered_revenue) FROM t GROUP BY report_date"

    assert "ordered_revenue" in infer_required_terms(sql)
    assert "GROUP BY report_date" in infer_required_terms(sql)
    assert "GROUP BY month" in infer_forbidden_terms(
        'column "report_date" must appear in the GROUP BY clause',
        "SELECT to_char(report_date, 'YYYY-MM') AS month FROM t GROUP BY month",
    )


def test_build_candidate_marks_negative_feedback() -> None:
    candidate = build_candidate(
        {
            "query_id": "q1",
            "created_at": "2026-07-14",
            "user_text": "看销售额",
            "status": "success",
            "feedback_values": "wrong_metric",
            "sql": "SELECT SUM(ordered_revenue) FROM intermediate_amazon_3p_orders_brumate_view WHERE report_date >= DATE '2026-06-01'",
            "error": "",
            "row_count": 1,
            "columns_json": '["sum"]',
            "selected_catalog_docs": '["intermediate_amazon.md"]',
        },
        1,
    )

    assert candidate["source_reasons"] == ["negative_feedback"]
    assert candidate["needs_human_review"] is True
    assert candidate["columns_json"] == ["sum"]
    assert candidate["expected_tables"] == ["intermediate_amazon_3p_orders_brumate_view"]


def test_generate_candidates_from_sqlite(tmp_path) -> None:
    db_path = tmp_path / "query_logs.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE query_events (
                query_id TEXT PRIMARY KEY,
                created_at TEXT,
                user_text TEXT,
                status TEXT,
                selected_catalog_docs TEXT,
                llm_response TEXT,
                sql TEXT,
                row_count INTEGER,
                columns_json TEXT,
                error TEXT,
                duration_ms INTEGER
            );
            CREATE TABLE feedback_events (
                feedback_id TEXT PRIMARY KEY,
                created_at TEXT,
                query_id TEXT,
                feedback TEXT,
                message_id TEXT,
                open_id TEXT,
                raw_action_json TEXT
            );
            INSERT INTO query_events VALUES (
                'q_error',
                datetime('now'),
                'Brumate 2026年6月份订单销售额数据',
                'error',
                '["intermediate_amazon.md"]',
                '',
                'SELECT to_char(report_date, ''YYYY-MM'') AS month FROM intermediate_amazon_3p_orders_brumate_view GROUP BY month',
                NULL,
                NULL,
                'must appear in the GROUP BY clause',
                100
            );
            INSERT INTO query_events VALUES (
                'q_ok',
                datetime('now'),
                '看销售额',
                'success',
                '["intermediate_amazon.md"]',
                '',
                'SELECT SUM(ordered_revenue) FROM intermediate_amazon_3p_orders_brumate_view WHERE report_date >= DATE ''2026-06-01''',
                1,
                '["sum"]',
                '',
                100
            );
            INSERT INTO feedback_events VALUES (
                'f1',
                datetime('now'),
                'q_ok',
                'wrong_metric',
                'm1',
                'u1',
                '{}'
            );
            """
        )

    candidates = generate_candidates(db_path, days=30)

    assert len(candidates) == 2
    assert {candidate["source_query_id"] for candidate in candidates} == {"q_error", "q_ok"}
    assert any("query_error" in candidate["source_reasons"] for candidate in candidates)
    assert any("negative_feedback" in candidate["source_reasons"] for candidate in candidates)
