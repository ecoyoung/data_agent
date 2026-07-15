from data_agent.config import get_settings
from data_agent.session import query_log


def test_query_log_records_query_and_feedback(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "query_logs.sqlite3"
    monkeypatch.setattr(get_settings(), "query_log_db_path", str(db_path))

    query_id = query_log.create_query_event(
        session_id="s1",
        message_id="om_1",
        chat_id="oc_1",
        user_text="看 2026年7月 Business Report sessions",
    )
    query_log.update_query_event(
        query_id,
        status="success",
        selected_catalog_docs=["intermediate_amazon.md"],
        sql="SELECT 1",
        row_count=1,
        columns_json=["ok"],
    )
    feedback_id = query_log.record_feedback(
        query_id=query_id,
        feedback="accurate",
        message_id="om_card",
        open_id="ou_1",
        raw_action={"action": "feedback"},
    )

    event = query_log.get_query_event(query_id)
    feedback = query_log.list_feedback(query_id)

    assert db_path.exists()
    assert feedback_id
    assert event is not None
    assert event["status"] == "success"
    assert event["sql"] == "SELECT 1"
    assert "intermediate_amazon.md" in event["selected_catalog_docs"]
    assert feedback[0]["feedback"] == "accurate"
    assert feedback[0]["message_id"] == "om_card"


def test_query_log_claims_message_once(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "query_logs.sqlite3"
    monkeypatch.setattr(get_settings(), "query_log_db_path", str(db_path))

    first_query_id, first_claimed = query_log.claim_message_query_event(
        session_id="s1",
        message_id="om_duplicate",
        chat_id="oc_1",
        user_text="Brumate 2026年6月 GMV 趋势",
    )
    second_query_id, second_claimed = query_log.claim_message_query_event(
        session_id="s1",
        message_id="om_duplicate",
        chat_id="oc_1",
        user_text="Brumate 2026年6月 GMV 趋势",
    )

    assert first_claimed is True
    assert second_claimed is False
    assert second_query_id == first_query_id

    event = query_log.get_query_event(first_query_id)
    assert event is not None
    assert event["message_id"] == "om_duplicate"
    assert event["status"] == "received"
