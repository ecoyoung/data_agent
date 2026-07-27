import json
from threading import BoundedSemaphore

from data_agent.feishu import webhook
from data_agent.config import get_settings
from data_agent.session.manager import clear_session
from data_agent.session.query_log import create_query_event, get_query_event, list_feedback


def setup_function() -> None:
    webhook._active_group_threads.clear()
    webhook._session_semaphores.clear()
    clear_session("s1")


def test_group_message_without_bot_mention_is_ignored(monkeypatch) -> None:
    monkeypatch.setattr(webhook, "get_bot_open_id", lambda: "ou_bot")

    should_handle, session_id = webhook._message_routing(
        {
            "message_id": "om_1",
            "chat_id": "oc_1",
            "chat_type": "group",
            "content": json.dumps({"text": "hello"}),
        }
    )

    assert should_handle is False
    assert session_id == ""


def test_group_message_with_bot_mention_activates_topic(monkeypatch) -> None:
    monkeypatch.setattr(webhook, "get_bot_open_id", lambda: "ou_bot")

    should_handle, session_id = webhook._message_routing(
        {
            "message_id": "om_root",
            "chat_id": "oc_1",
            "chat_type": "group",
            "mentions": [{"id": {"open_id": "ou_bot"}}],
            "content": json.dumps({"text": '<at user_id="ou_bot">bot</at> hello'}),
        }
    )

    assert should_handle is True
    assert session_id == "om_root"
    assert "om_root" in webhook._active_group_threads


def test_group_thread_message_only_works_for_active_topic(monkeypatch) -> None:
    monkeypatch.setattr(webhook, "get_bot_open_id", lambda: "ou_bot")

    should_handle, _ = webhook._message_routing(
        {
            "message_id": "om_reply",
            "chat_id": "oc_1",
            "chat_type": "group",
            "thread_id": "om_root",
            "content": json.dumps({"text": "follow up"}),
        }
    )
    assert should_handle is False

    webhook._active_group_threads.add("om_root")
    should_handle, session_id = webhook._message_routing(
        {
            "message_id": "om_reply",
            "chat_id": "oc_1",
            "chat_type": "group",
            "thread_id": "om_root",
            "content": json.dumps({"text": "follow up"}),
        }
    )

    assert should_handle is True
    assert session_id == "om_root"


def test_direct_message_still_works() -> None:
    should_handle, session_id = webhook._message_routing(
        {
            "message_id": "om_1",
            "chat_id": "oc_dm",
            "chat_type": "p2p",
            "content": json.dumps({"text": "hello"}),
        }
    )

    assert should_handle is True
    assert session_id == "oc_dm"


def test_handle_user_query_clarifies_before_llm_when_time_missing(monkeypatch) -> None:
    def fail_if_called(_messages):
        raise AssertionError("LLM should not be called for clarification")

    monkeypatch.setattr(webhook, "chat", fail_if_called)

    card = webhook._handle_user_query("s1", "看一下销售额")

    assert card["header"]["title"]["content"] == "需要确认信息"
    assert "查询时间范围" in str(card)


def test_handle_user_query_calls_llm_for_generic_sales_with_time(monkeypatch) -> None:
    called = {"chat": False, "execute": False}

    def fake_chat(messages):
        called["chat"] = True
        system = messages[0]["content"]
        assert "SUM(ordered_revenue)" in system
        assert "to_char(report_date, 'YYYY-MM')" in system
        return "结果如下\n```sql\nSELECT 1 AS ok\n```"

    def fake_execute(_sql):
        called["execute"] = True
        return [{"ok": 1}], ["ok"], None

    monkeypatch.setattr(webhook, "chat", fake_chat)
    monkeypatch.setattr(webhook, "execute_query", fake_execute)
    monkeypatch.setattr(webhook, "upload_image", lambda _bytes: "img_key")

    card = webhook._handle_user_query("s1", "看一下 2026年7月 销售额")

    assert called == {"chat": True, "execute": True}
    assert card["header"]["title"]["content"].startswith("看一下 2026年7月")


def test_handle_user_query_calls_llm_when_question_is_clear(monkeypatch) -> None:
    called = {"chat": False, "execute": False}

    def fake_chat(_messages):
        called["chat"] = True
        return "结果如下\n```sql\nSELECT 1 AS ok\n```"

    def fake_execute(_sql):
        called["execute"] = True
        return [{"ok": 1}], ["ok"], None

    monkeypatch.setattr(webhook, "chat", fake_chat)
    monkeypatch.setattr(webhook, "execute_query", fake_execute)
    monkeypatch.setattr(webhook, "upload_image", lambda _bytes: "img_key")

    card = webhook._handle_user_query("s1", "看 2026年7月 Business Report 销售额和 sessions")

    assert called == {"chat": True, "execute": True}
    assert card["header"]["title"]["content"].startswith("看 2026年7月")


def test_handle_user_query_uses_line_chart_and_full_table_for_daily_trend(monkeypatch) -> None:
    called = {"line": False, "bar": False}

    monkeypatch.setattr(
        webhook,
        "chat",
        lambda _messages: (
            "结果如下\n```sql\n"
            "SELECT report_date, SUM(ordered_revenue) AS sales "
            "FROM intermediate_amazon_3p_orders_brumate_view "
            "WHERE report_date >= DATE '2026-06-01' AND report_date < DATE '2026-07-01' "
            "GROUP BY report_date ORDER BY report_date;\n```"
        ),
    )
    monkeypatch.setattr(
        webhook,
        "execute_query",
        lambda _sql: (
            [
                {"report_date": f"2026-06-{day:02d}", "sales": float(day)}
                for day in range(1, 31)
            ],
            ["report_date", "sales"],
            None,
        ),
    )

    def fake_line_chart(*_args, **_kwargs):
        called["line"] = True
        return b"line_png"

    def fake_bar_chart(*_args, **_kwargs):
        called["bar"] = True
        return b"bar_png"

    monkeypatch.setattr("data_agent.visualization.chart.generate_line_chart", fake_line_chart)
    monkeypatch.setattr("data_agent.visualization.chart.generate_bar_chart", fake_bar_chart)
    monkeypatch.setattr("data_agent.visualization.chart.generate_table_image", lambda *_args, **_kwargs: b"table_png")
    monkeypatch.setattr(webhook, "upload_image", lambda chart_bytes: chart_bytes.decode())

    card = webhook._handle_user_query("s1", "Brumate 2026年6月份订单销售额趋势")
    card_text = str(card)

    assert called == {"line": True, "bar": False}
    assert "line_png" in card_text
    assert "table_png" in card_text
    assert "展示前 10 行" not in card_text


def test_handle_user_query_removes_llm_demo_table_from_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        webhook,
        "chat",
        lambda _messages: (
            "根据您的确认，以下 SQL 查询 2026 年 5 月和 6 月的店铺订单销售额和销量。\n"
            "执行结果示意：\n\n"
            "| month | revenue | units |\n"
            "| --- | --- | --- |\n"
            "| 2026-05 | 125,000.00 | 2,500 |\n"
            "如果您需要查看更多维度，请随时说明。\n"
            "```sql\nSELECT '2026-05' AS month, 1 AS revenue, 2 AS units\n```"
        ),
    )
    monkeypatch.setattr(
        webhook,
        "execute_query",
        lambda _sql: (
            [
                {"month": "2026-05", "revenue": 125000.0, "units": 2500},
                {"month": "2026-06", "revenue": 138000.0, "units": 2700},
            ],
            ["month", "revenue", "units"],
            None,
        ),
    )
    monkeypatch.setattr(webhook, "upload_image", lambda _bytes: None)

    card = webhook._handle_user_query("s1", "BKN US 2026年5月和6月销售额销量环比")
    body = str(card)

    assert "执行结果示意" not in body
    assert "如果您需要" not in body
    assert "| month | revenue | units |" not in body
    assert "$125,000.00" in body
    assert "2,700" in body


def test_handle_user_query_uploads_chart_and_full_table_images(monkeypatch) -> None:
    monkeypatch.setattr(
        webhook,
        "chat",
        lambda _messages: "```sql\nSELECT '2026-06' AS month, 1 AS sales, 2 AS units\n```",
    )
    monkeypatch.setattr(
        webhook,
        "execute_query",
        lambda _sql: (
            [
                {
                    "month": "2026-06",
                    "sales": 100.0,
                    "units": 10,
                    "sales_change": -7.0,
                    "sales_change_pct": -0.07,
                    "units_change": -1,
                    "units_change_pct": -0.1,
                }
            ],
            [
                "month",
                "sales",
                "units",
                "sales_change",
                "sales_change_pct",
                "units_change",
                "units_change_pct",
            ],
            None,
        ),
    )
    monkeypatch.setattr("data_agent.visualization.chart.generate_table_image", lambda *_args, **_kwargs: b"table_png")

    uploaded: list[bytes] = []

    def fake_upload(payload: bytes) -> str:
        uploaded.append(payload)
        return f"img_{len(uploaded)}"

    monkeypatch.setattr(webhook, "upload_image", fake_upload)

    card = webhook._handle_user_query("s1", "BKN US 2026年6月销售额销量环比")
    body = str(card)

    assert uploaded[-1] == b"table_png"
    assert "img_2" in body
    assert "原始数据" in body
    assert "| month | sales | units | sales_change | sales_change_pct | units_change | units_change_pct |" in body
    assert "共 7 列（展示前 6 列）" not in body


def test_handle_user_query_skips_chart_but_uploads_table_for_detail_intent(monkeypatch) -> None:
    uploaded: list[bytes] = []

    monkeypatch.setattr(
        webhook,
        "chat",
        lambda _messages: "结果如下\n```sql\nSELECT report_date, sku, ordered_revenue FROM t LIMIT 30\n```",
    )
    monkeypatch.setattr(
        webhook,
        "execute_query",
        lambda _sql: (
            [{"report_date": "2026-06-01", "sku": "SKU-1", "ordered_revenue": 10.0}],
            ["report_date", "sku", "ordered_revenue"],
            None,
        ),
    )

    monkeypatch.setattr("data_agent.visualization.chart.generate_table_image", lambda *_args, **_kwargs: b"table_png")

    def fake_upload(payload: bytes):
        uploaded.append(payload)
        return "table_img"

    monkeypatch.setattr(webhook, "upload_image", fake_upload)

    card = webhook._handle_user_query("s1", "Brumate 2026年6月订单明细列表")

    assert uploaded == [b"table_png"]
    assert "table_img" in str(card)


def test_handle_user_query_retries_once_with_repaired_sql(monkeypatch) -> None:
    chat_responses = iter(
        [
            "结果如下\n```sql\nSELECT bad_sql\n```",
            "```sql\nSELECT 1 AS ok\n```",
        ]
    )
    executed: list[str] = []

    monkeypatch.setattr(webhook, "chat", lambda _messages: next(chat_responses))
    monkeypatch.setattr(webhook, "_maybe_refine_tables_via_llm", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(webhook, "_maybe_find_few_shot_examples", lambda *_args, **_kwargs: [])

    def fake_execute(sql: str):
        executed.append(sql)
        if sql == "SELECT bad_sql":
            return [], [], "数据库错误：column bad_sql does not exist"
        return [{"ok": 1}], ["ok"], None

    monkeypatch.setattr(webhook, "execute_query", fake_execute)
    monkeypatch.setattr(webhook, "upload_image", lambda _bytes: None)

    card = webhook._handle_user_query("s1", "看 2026年7月 销售额")

    assert executed == ["SELECT bad_sql", "SELECT 1 AS ok"]
    assert card["header"]["title"]["content"].startswith("看 2026年7月")
    assert "1" in str(card)


def test_handle_user_query_reports_retry_error_when_repaired_sql_fails(monkeypatch) -> None:
    chat_responses = iter(
        [
            "结果如下\n```sql\nSELECT bad_sql\n```",
            "```sql\nSELECT still_bad\n```",
        ]
    )

    monkeypatch.setattr(webhook, "chat", lambda _messages: next(chat_responses))
    monkeypatch.setattr(webhook, "_maybe_refine_tables_via_llm", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(webhook, "_maybe_find_few_shot_examples", lambda *_args, **_kwargs: [])

    def fake_execute(sql: str):
        if sql == "SELECT bad_sql":
            return [], [], "数据库错误：operator does not exist: text = date"
        return [], [], "业务规则校验失败：表 t 引用了不存在的列：country"

    monkeypatch.setattr(webhook, "execute_query", fake_execute)

    card = webhook._handle_user_query("s1", "看 2026年7月 销售额")

    rendered = str(card)
    assert "operator does not exist" in rendered
    assert "重试 SQL 仍出错" in rendered
    assert "不存在的列：country" in rendered


def test_handle_user_query_does_not_retry_permission_errors(monkeypatch) -> None:
    monkeypatch.setattr(webhook, "chat", lambda _messages: "```sql\nSELECT bad_sql\n```")
    monkeypatch.setattr(webhook, "_maybe_refine_tables_via_llm", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(webhook, "_maybe_find_few_shot_examples", lambda *_args, **_kwargs: [])

    executed: list[str] = []

    def fake_execute(sql: str):
        executed.append(sql)
        return [], [], "数据库权限不足：当前数据库用户没有 SELECT 权限：intermediate_amazon_3p_orders_blueland_view"

    def fail_repair(**_kwargs):
        raise AssertionError("permission errors should not be sent to LLM repair")

    monkeypatch.setattr(webhook, "execute_query", fake_execute)
    monkeypatch.setattr(webhook, "_repair_sql_via_llm", fail_repair)

    card = webhook._handle_user_query("s1", "blueland 2026-07-14 店铺销售额、销量")

    rendered = str(card)
    assert executed == ["SELECT bad_sql"]
    assert "数据库权限不足" in rendered
    assert "重试 SQL 仍出错" not in rendered


def test_handle_user_query_does_not_retry_timeout_errors(monkeypatch) -> None:
    monkeypatch.setattr(webhook, "chat", lambda _messages: "```sql\nSELECT slow_sql\n```")
    monkeypatch.setattr(webhook, "_maybe_refine_tables_via_llm", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(webhook, "_maybe_find_few_shot_examples", lambda *_args, **_kwargs: [])

    executed: list[str] = []

    def fake_execute(sql: str):
        executed.append(sql)
        return [], [], "查询超时（超过 30 秒），请缩小时间范围或增加过滤条件"

    def fail_repair(**_kwargs):
        raise AssertionError("timeout errors should not be sent to LLM repair")

    monkeypatch.setattr(webhook, "execute_query", fake_execute)
    monkeypatch.setattr(webhook, "_repair_sql_via_llm", fail_repair)

    card = webhook._handle_user_query("s1", "BKN US 2026年1到6月店铺销售额销量环比")

    rendered = str(card)
    assert executed == ["SELECT slow_sql"]
    assert "查询超时" in rendered
    assert "重试 SQL 仍出错" not in rendered


def test_handle_user_query_clarifies_ambiguous_scope_alias(monkeypatch) -> None:
    def fail_chat(_messages):
        raise AssertionError("ambiguous scope should be clarified before LLM")

    monkeypatch.setattr(webhook, "chat", fail_chat)

    card = webhook._handle_user_query("s1", "BKN 2026-07-14 销售额")

    rendered = str(card)
    assert "对应多个可查询范围" in rendered
    assert "US" in rendered
    assert "CA" in rendered


def test_handle_user_query_updates_query_log(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(get_settings(), "query_log_db_path", str(tmp_path / "query_logs.sqlite3"))
    query_id = create_query_event(
        session_id="s1",
        user_text="看 2026年7月 Business Report 销售额和 sessions",
        message_id="om_1",
        chat_id="oc_1",
    )

    monkeypatch.setattr(
        webhook,
        "chat",
        lambda _messages: "结果如下\n```sql\nSELECT 1 AS ok\n```",
    )
    monkeypatch.setattr(
        webhook,
        "execute_query",
        lambda _sql: ([{"ok": 1}], ["ok"], None),
    )
    monkeypatch.setattr(webhook, "upload_image", lambda _bytes: None)

    card = webhook._handle_user_query(
        "s1",
        "看 2026年7月 Business Report 销售额和 sessions",
        query_id=query_id,
    )
    event = get_query_event(query_id)

    assert event is not None
    assert event["status"] == "success"
    assert event["sql"] == "SELECT 1 AS ok"
    assert event["row_count"] == 1
    assert query_id in str(card)


def test_process_message_event_is_idempotent_by_message_id(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(get_settings(), "query_log_db_path", str(tmp_path / "query_logs.sqlite3"))
    calls = {"handle": 0, "send": 0}

    def fake_handle_user_query(session_id, user_text, query_id=None):
        calls["handle"] += 1
        return {"header": {"title": {"content": "ok"}}, "elements": [], "query_id": query_id}

    monkeypatch.setattr(webhook, "_handle_user_query", fake_handle_user_query)
    monkeypatch.setattr(webhook, "_send_initial_feedback", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        webhook,
        "_send_card",
        lambda *_args, **_kwargs: calls.__setitem__("send", calls["send"] + 1) or "om_sent",
    )

    message = {
        "message_id": "om_duplicate",
        "chat_id": "oc_1",
        "chat_type": "p2p",
    }

    first = webhook._process_message_event({}, message, "s1", "Brumate 2026年6月 GMV 趋势", "om_duplicate")
    second = webhook._process_message_event({}, message, "s1", "Brumate 2026年6月 GMV 趋势", "om_duplicate")

    assert first == {"code": 0}
    assert second == {"code": 0}
    assert calls == {"handle": 1, "send": 1}


def test_handle_user_query_with_limit_returns_busy_without_processing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(get_settings(), "query_log_db_path", str(tmp_path / "query_logs.sqlite3"))
    query_id = create_query_event(session_id="s_busy", user_text="Brumate 2026年6月 GMV 趋势")
    semaphore = BoundedSemaphore(1)
    assert semaphore.acquire(blocking=False) is True
    monkeypatch.setattr(webhook, "_query_semaphore", semaphore)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("query should not run when concurrency limit is saturated")

    monkeypatch.setattr(webhook, "_handle_user_query", fail_if_called)

    card = webhook._handle_user_query_with_limit(
        "s_busy",
        "Brumate 2026年6月 GMV 趋势",
        query_id=query_id,
    )
    event = get_query_event(query_id)

    assert "系统正在处理较多查询" in str(card)
    assert event is not None
    assert event["status"] == "error"
    assert "max concurrent queries" in event["error"]


def test_handle_user_query_with_limit_serializes_same_session(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(get_settings(), "query_log_db_path", str(tmp_path / "query_logs.sqlite3"))
    query_id = create_query_event(session_id="s_locked", user_text="第二个问题")
    session_semaphore = webhook._get_session_semaphore("s_locked")
    assert session_semaphore.acquire(blocking=False) is True

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("same-session concurrent query should not run")

    monkeypatch.setattr(webhook, "_handle_user_query", fail_if_called)

    card = webhook._handle_user_query_with_limit("s_locked", "第二个问题", query_id=query_id)
    event = get_query_event(query_id)

    assert "上一条查询还在处理" in str(card)
    assert event is not None
    assert event["status"] == "error"
    assert "session busy" in event["error"]

    session_semaphore.release()


def test_handle_user_query_with_limit_allows_different_sessions(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(get_settings(), "query_log_db_path", str(tmp_path / "query_logs.sqlite3"))
    locked = webhook._get_session_semaphore("s_locked")
    assert locked.acquire(blocking=False) is True
    calls = []

    def fake_handle(session_id, user_text, query_id=None):
        calls.append((session_id, user_text, query_id))
        return {"header": {"title": {"content": "ok"}}, "elements": []}

    monkeypatch.setattr(webhook, "_handle_user_query", fake_handle)

    card = webhook._handle_user_query_with_limit("s_other", "另一个会话的问题")

    assert "ok" in str(card)
    assert calls == [("s_other", "另一个会话的问题", None)]
    locked.release()


def test_card_action_trigger_show_sql_replies_to_card_message(monkeypatch) -> None:
    sent = {}

    def fake_reply(message_id, card, reply_in_thread=True):
        sent["message_id"] = message_id
        sent["card"] = card
        sent["reply_in_thread"] = reply_in_thread
        return "om_reply"

    monkeypatch.setattr(webhook, "reply_to_message", fake_reply)

    response = webhook._handle_card_action(
        {
            "header": {"event_type": "card.action.trigger"},
            "event": {
                "context": {"open_message_id": "om_card"},
                "action": {
                    "value": {
                        "action": "show_sql",
                        "sql": "SELECT 1",
                    }
                },
            },
        }
    )

    assert response == {"code": 0}
    assert sent["message_id"] == "om_card"
    assert sent["reply_in_thread"] is True
    assert "SELECT 1" in str(sent["card"])


def test_card_action_trigger_supports_string_value(monkeypatch) -> None:
    sent = {}
    monkeypatch.setattr(
        webhook,
        "reply_to_message",
        lambda message_id, card, reply_in_thread=True: sent.update(
            {"message_id": message_id, "card": card}
        )
        or "om_reply",
    )

    response = webhook._handle_card_action(
        {
            "event": {
                "message_id": "om_card",
                "action": {
                    "value": json.dumps({"action": "show_trend"}, ensure_ascii=False)
                },
            }
        }
    )

    assert response == {"code": 0}
    assert sent["message_id"] == "om_card"
    assert "趋势" in str(sent["card"])


def test_card_action_trigger_feedback_records_sqlite(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(get_settings(), "query_log_db_path", str(tmp_path / "query_logs.sqlite3"))
    query_id = create_query_event(session_id="s1", user_text="question")
    sent = {}
    monkeypatch.setattr(
        webhook,
        "reply_to_message",
        lambda message_id, card, reply_in_thread=True: sent.update(
            {"message_id": message_id, "card": card}
        )
        or "om_reply",
    )

    response = webhook._handle_card_action(
        {
            "event": {
                "context": {"open_message_id": "om_card"},
                "operator": {"operator_id": {"open_id": "ou_1"}},
                "action": {
                    "value": {
                        "action": "feedback",
                        "feedback": "wrong_metric",
                        "query_id": query_id,
                    }
                },
            }
        }
    )

    feedback = list_feedback(query_id)

    assert response == {"code": 0}
    assert sent["message_id"] == "om_card"
    assert "反馈已记录" in str(sent["card"])
    assert feedback[0]["feedback"] == "wrong_metric"
    assert feedback[0]["open_id"] == "ou_1"


def test_handle_user_query_clarification_card_has_reset_button(monkeypatch) -> None:
    def fail_if_called(_messages):
        raise AssertionError("LLM should not be called for clarification")

    monkeypatch.setattr(webhook, "chat", fail_if_called)
    clear_session("s_reset")

    card = webhook._handle_user_query("s_reset", "看一下销售额")  # no time → clarifies

    actions = [
        action
        for element in card["elements"]
        if element.get("tag") == "action"
        for action in element.get("actions", [])
    ]
    reset = [a for a in actions if a["value"].get("action") == "reset_session"]
    assert reset
    assert reset[0]["value"]["session_id"] == "s_reset"


def test_card_action_reset_session_clears_history(monkeypatch) -> None:
    from data_agent.session.manager import add_to_history, get_history

    add_to_history("s_reset_action", "user", "旧问题")
    assert get_history("s_reset_action")

    sent = {}
    monkeypatch.setattr(
        webhook,
        "reply_to_message",
        lambda message_id, card, reply_in_thread=True: sent.update(
            {"message_id": message_id, "card": card}
        )
        or "om_reply",
    )

    response = webhook._handle_card_action(
        {
            "header": {"event_type": "card.action.trigger"},
            "event": {
                "context": {"open_message_id": "om_card"},
                "action": {
                    "value": {"action": "reset_session", "session_id": "s_reset_action"}
                },
            },
        }
    )

    assert response == {"code": 0}
    assert get_history("s_reset_action") == []
    assert "已重置" in str(sent["card"])


def test_handle_user_query_returns_error_card_on_llm_timeout(monkeypatch) -> None:
    from data_agent.agent.llm_client import LLMTimeoutError

    def fake_chat(_messages):
        raise LLMTimeoutError("simulated")

    monkeypatch.setattr(webhook, "chat", fake_chat)

    card = webhook._handle_user_query(
        "s1",
        "看 2026年7月 Business Report 销售额和 sessions",  # passes clarifier
    )

    assert card["header"]["title"]["content"] == "查询遇到问题"
    assert "60 秒" in str(card)
