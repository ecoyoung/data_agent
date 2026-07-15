import json
from decimal import Decimal

from data_agent.feishu.card_builder import (
    build_empty_result_card,
    build_result_card,
    build_sql_card,
)


def _all_actions(card: dict) -> list[dict]:
    """Flatten action buttons AND overflow options into a single list.

    Each returned item has the same shape: ``{"value": {...}}`` plus optional
    display fields. Overflow options store their value as a JSON-encoded
    string (Feishu requires this); we parse it back to a dict so callers can
    uniformly inspect ``action["value"]``.
    """
    collected: list[dict] = []
    for element in card["elements"]:
        if element.get("tag") != "action":
            continue
        for action in element.get("actions", []):
            if action.get("tag") == "overflow":
                for option in action.get("options", []):
                    raw_value = option.get("value", "")
                    if isinstance(raw_value, str):
                        try:
                            value = json.loads(raw_value)
                        except json.JSONDecodeError:
                            value = {}
                    else:
                        value = raw_value
                    collected.append({"value": value})
            else:
                collected.append(action)
    return collected


def test_result_card_uses_structured_table_and_hides_sql_by_default() -> None:
    card = build_result_card(
        title="title",
        summary="summary",
        table_markdown="| a |\n| --- |\n| 1 |",
        sql="SELECT 1",
        query_id="qid_1",
        table_rows=[{"asin": "B001", "sessions": 123, "rate": 0.1234}],
        columns=["asin", "sessions", "rate"],
    )

    tags = [element.get("tag") for element in card["elements"]]
    assert "column_set" in tags
    assert "collapse" not in tags
    visible_markdown = [
        element.get("content", "")
        for element in card["elements"]
        if element.get("tag") == "markdown"
    ]
    assert not any("SELECT 1" in content for content in visible_markdown)

    actions = _all_actions(card)
    show_sql = [action for action in actions if action["value"]["action"] == "show_sql"]
    assert show_sql
    assert show_sql[0]["value"]["sql"] == "SELECT 1"
    assert show_sql[0]["value"]["query_id"] == "qid_1"

    feedback = [action for action in actions if action["value"]["action"] == "feedback"]
    assert {action["value"]["feedback"] for action in feedback} == {
        "accurate",
        "wrong_metric",
        "not_what_i_wanted",
    }
    assert all(action["value"]["query_id"] == "qid_1" for action in feedback)


def test_result_card_formats_percent_cells() -> None:
    card = build_result_card(
        title="title",
        summary="",
        table_markdown="",
        table_rows=[{"asin": "B001", "conversion_rate": 0.1234, "acos": 0.4567}],
        columns=["asin", "conversion_rate", "acos"],
    )

    assert "12.34%" in str(card)
    assert "45.67%" in str(card)


def test_result_card_formats_decimal_values_from_postgres_numeric() -> None:
    """PostgreSQL numeric columns arrive as Decimal, not float. They must still
    be formatted as money / percent rather than dumped as raw strings."""
    card = build_result_card(
        title="title",
        summary="",
        table_markdown="",
        table_rows=[
            {
                "asin": "B001",
                "ad_spend": Decimal("28633.99"),
                "business_report_sales": Decimal("86732.9100"),
                "acos": Decimal("0.9687"),
            }
        ],
        columns=["asin", "ad_spend", "business_report_sales", "acos"],
    )

    body = str(card)
    assert "$28,633.99" in body
    assert "$86,732.91" in body
    assert "96.87%" in body
    assert "86732.9100" not in body
    assert "0.9687" not in body


def test_result_card_preserves_full_column_header() -> None:
    card = build_result_card(
        title="title",
        summary="",
        table_markdown="",
        table_rows=[{"asin": "B001", "business_report_sales": 100.0}],
        columns=["asin", "business_report_sales"],
    )

    body = str(card)
    # Full header preserved (underscores → spaces), not truncated.
    assert "business report sales" in body
    assert "…" not in body


def test_sql_card_contains_sql() -> None:
    card = build_sql_card("SELECT 1")

    assert "SELECT 1" in str(card)


def test_result_card_highlights_single_numeric_value() -> None:
    card = build_result_card(
        title="title",
        summary="",
        table_markdown="",
        sql="SELECT 1",
        query_id="qid_single",
        table_rows=[{"total_sales": 123456.78}],
        columns=["total_sales"],
    )

    body = str(card)
    assert "# $123,456.78" in body
    tags = [element.get("tag") for element in card["elements"]]
    assert "img" not in tags
    assert "column_set" not in tags


def test_result_card_preserves_full_summary_text() -> None:
    long_summary = " ".join(["摘要段落"] * 60)
    card = build_result_card(
        title="title",
        summary=long_summary,
        table_markdown="",
        table_rows=[{"asin": "B001", "sessions": 1}],
        columns=["asin", "sessions"],
    )

    summaries = [
        element.get("content", "")
        for element in card["elements"]
        if element.get("tag") == "markdown"
    ]
    joined = " ".join(summaries)
    # Full content is preserved; no truncation marker.
    assert long_summary in joined
    assert "…" not in joined
    assert "collapse" not in [element.get("tag") for element in card["elements"]]


def test_empty_result_card_hides_drill_actions_and_keeps_feedback() -> None:
    card = build_empty_result_card(
        title="无数据查询",
        summary="some summary",
        sql="SELECT 1",
        query_id="qid_empty",
    )

    assert card["header"]["template"] == "grey"
    body = str(card)
    assert "未查到数据" in body
    assert "下钻明细" not in body
    assert "看趋势图" not in body
    assert "查看 SQL" in body

    actions = _all_actions(card)
    feedback_kinds = {action["value"]["feedback"] for action in actions if action["value"].get("action") == "feedback"}
    assert feedback_kinds == {"accurate", "wrong_metric", "not_what_i_wanted"}


def test_empty_result_card_without_sql_still_shows_feedback() -> None:
    card = build_empty_result_card(title="empty", summary="", sql=None, query_id="qid_empty")

    actions = _all_actions(card)
    assert any(action["value"].get("action") == "feedback" for action in actions)
    assert not any(action["value"].get("action") == "show_sql" for action in actions)
