from pathlib import Path

from data_agent.config import get_settings
from data_agent.session.query_log import create_query_event, record_feedback, update_query_event
from scripts.review_feedback import fetch_feedback, render_report


def test_review_feedback_exports_only_review_items_by_default(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "query_logs.sqlite3"
    monkeypatch.setattr(get_settings(), "query_log_db_path", str(db_path))

    good_query = create_query_event(session_id="s1", user_text="good question")
    record_feedback(query_id=good_query, feedback="accurate")

    bad_query = create_query_event(session_id="s2", user_text="bad question")
    update_query_event(
        bad_query,
        status="success",
        selected_catalog_docs=["intermediate_amazon.md"],
        sql="SELECT 1",
        row_count=1,
    )
    record_feedback(query_id=bad_query, feedback="wrong_metric")

    rows = fetch_feedback(Path(db_path), days=None, include_accurate=False)
    report = render_report(rows, Path(db_path), days=None, include_accurate=False)

    assert len(rows) == 1
    assert rows[0]["query_id"] == bad_query
    assert "口径不对" in report
    assert "bad question" in report
    assert "good question" not in report
    assert "```sql\nSELECT 1\n```" in report


def test_review_feedback_can_include_accurate_feedback(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "query_logs.sqlite3"
    monkeypatch.setattr(get_settings(), "query_log_db_path", str(db_path))

    query_id = create_query_event(session_id="s1", user_text="good question")
    record_feedback(query_id=query_id, feedback="accurate")

    rows = fetch_feedback(Path(db_path), days=None, include_accurate=True)
    report = render_report(rows, Path(db_path), days=None, include_accurate=True)

    assert len(rows) == 1
    assert "准确" in report
    assert "good question" in report
