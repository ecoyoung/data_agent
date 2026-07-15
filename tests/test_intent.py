from data_agent.agent.intent import infer_query_intent, render_intent_prompt


def test_infer_query_intent_detects_trend() -> None:
    intent = infer_query_intent("Brumate 2026年6月份订单销售额趋势")

    assert intent.name == "trend"
    assert intent.chart_type == "line"
    assert intent.table_max_rows == 31
    assert "report_date" in intent.sql_guidance


def test_infer_query_intent_detects_ranking() -> None:
    intent = infer_query_intent("2026年6月广告花费最多的10个 ASIN")

    assert intent.name == "ranking"
    assert intent.chart_type == "bar"
    assert "LIMIT 20" in intent.sql_guidance


def test_render_intent_prompt_is_compact() -> None:
    prompt = render_intent_prompt("对比 2026年6月 Belli Welli 和 Brumate 销售额")

    assert "Query Intent" in prompt
    assert "intent: `comparison`" in prompt
    assert "preferred_chart" in prompt
