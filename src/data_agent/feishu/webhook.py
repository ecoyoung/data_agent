from __future__ import annotations

import hashlib
import hmac
import json
import re
from threading import BoundedSemaphore, Lock
import time

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from lark_oapi.core.utils import AESCipher

from data_agent.agent.clarifier import needs_clarification
from data_agent.agent.intent import infer_query_intent
from data_agent.agent.llm_client import LLMTimeoutError, chat, extract_sql, strip_sql_blocks
from data_agent.agent.prompt_builder import (
    _tables_referenced_by_docs,
    build_messages,
    refine_tables_via_llm,
    select_catalog_table_docs,
)
from data_agent.agent.sql_executor import execute_query
from data_agent.config import get_settings
from data_agent.feishu.card_builder import (
    build_clarification_card,
    build_empty_result_card,
    build_error_card,
    build_feedback_ack_card,
    build_result_card,
    build_sql_card,
    build_thinking_card,
)
from data_agent.feishu.sender import get_bot_open_id, reply_to_message, send_card_message, upload_image
from data_agent.session.manager import add_to_history, clear_session, get_history
from data_agent.session.query_log import claim_message_query_event, record_feedback, update_query_event


router = APIRouter()
_active_group_threads: set[str] = set()
_query_semaphore = BoundedSemaphore(get_settings().max_concurrent_queries)
_session_semaphores: dict[str, BoundedSemaphore] = {}
_session_semaphores_lock = Lock()


def _repair_sql_via_llm(
    *,
    user_text: str,
    sql: str,
    error: str,
    history: list[dict],
    selected_tables: list[str] | None,
    few_shot_examples: list[dict] | None,
) -> tuple[str | None, str]:
    repair_prompt = (
        "上一次 SQL 执行失败。请只输出修正后的 PostgreSQL SQL 代码块，"
        "不要解释、不要 markdown 之外的文字。必须保留用户原始业务意图，"
        "仍然只能使用 Data Catalog 中允许的中间表和字段。\n\n"
        f"用户问题：{user_text}\n\n"
        f"失败 SQL：\n```sql\n{sql}\n```\n\n"
        f"错误信息：{error}"
    )
    try:
        response = chat(
            build_messages(
                history,
                repair_prompt,
                selected_tables=selected_tables,
                few_shot_examples=few_shot_examples,
            )
        )
    except Exception as exc:
        return None, f"LLM repair failed: {type(exc).__name__}: {exc}"

    repaired_sql = extract_sql(response)
    if not repaired_sql:
        return None, "LLM repair did not return SQL"
    return repaired_sql, response


def verify_signature(timestamp: str, nonce: str, body: bytes, signature: str) -> bool:
    settings = get_settings()
    if not signature:
        return False
    content = timestamp + nonce + settings.feishu_encrypt_key + body.decode("utf-8")
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/feishu/webhook")
async def feishu_webhook(request: Request):
    body = await request.body()
    data = json.loads(body or b"{}")
    settings = get_settings()
    print(
        "[feishu] webhook received "
        f"keys={sorted(data.keys())} "
        f"has_challenge={bool(data.get('challenge'))} "
        f"has_encrypt={bool(data.get('encrypt'))}",
        flush=True,
    )

    if data.get("encrypt"):
        if not settings.feishu_encrypt_key:
            print("[feishu] encrypted event received but FEISHU_ENCRYPT_KEY is empty", flush=True)
            return {"code": 0}
        try:
            plaintext = AESCipher(settings.feishu_encrypt_key).decrypt_str(data["encrypt"])
            data = json.loads(plaintext)
            print(
                "[feishu] encrypted event decrypted "
                f"keys={sorted(data.keys())} "
                f"event_type={data.get('header', {}).get('event_type', '')!r}",
                flush=True,
            )
        except Exception as exc:
            print(f"[feishu] decrypt encrypted event failed: {type(exc).__name__}: {exc}", flush=True)
            return {"code": 0}

    if "challenge" in data:
        print("[feishu] url verification challenge handled", flush=True)
        return {"challenge": data["challenge"]}

    if settings.feishu_encrypt_key and settings.feishu_verification_token:
        if data.get("token") and data["token"] != settings.feishu_verification_token:
            return Response(status_code=401, content="Invalid verification token")

        timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        nonce = request.headers.get("X-Lark-Request-Nonce", "")
        signature = request.headers.get("X-Lark-Signature", "")
        if signature and not verify_signature(timestamp, nonce, body, signature):
            return Response(status_code=401, content="Invalid signature")

    event_type = data.get("header", {}).get("event_type", "")
    if event_type == "card.action.trigger":
        print("[feishu] card action trigger received via webhook", flush=True)
        return _handle_card_action(data)

    if event_type != "im.message.receive_v1":
        print(f"[feishu] ignored event_type={event_type!r}", flush=True)
        return {"code": 0}

    event = data.get("event", {})
    message = event.get("message", {})
    message_id = message.get("message_id", "")

    should_handle, session_id = _message_routing(message)
    if not should_handle:
        print("[feishu] ignored group message outside active bot topic", flush=True)
        return {"code": 0}

    user_text = _extract_user_text(message)
    print(
        "[feishu] message event "
        f"message_id={message_id!r} "
        f"chat_type={message.get('chat_type', '')!r} "
        f"message_type={message.get('message_type', '')!r} "
        f"thread_id={message.get('thread_id', '')!r} "
        f"text_present={bool(user_text)}",
        flush=True,
    )
    if not user_text:
        return {"code": 0}

    return await run_in_threadpool(
        _process_message_event,
        event,
        message,
        session_id,
        user_text,
        message_id,
    )


def _process_message_event(
    event: dict,
    message: dict,
    session_id: str,
    user_text: str,
    message_id: str,
) -> dict:
    chat_id = message.get("chat_id", "")
    chat_type = message.get("chat_type", "")

    query_id, claimed = claim_message_query_event(
        session_id=session_id,
        user_text=user_text,
        message_id=message_id,
        chat_id=chat_id,
    )
    if not claimed:
        print(
            "[feishu] duplicate message delivery ignored "
            f"message_id={message_id!r} query_id={query_id!r}",
            flush=True,
        )
        return {"code": 0}

    thinking_message_id = _send_initial_feedback(event, message, chat_id, chat_type)
    card = _handle_user_query_with_limit(session_id, user_text, query_id=query_id)

    try:
        if thinking_message_id:
            reply_to_message(thinking_message_id, card, reply_in_thread=(chat_type == "group"))
        else:
            _send_card(event, message, chat_id, chat_type, card)
    except Exception as exc:
        print(f"[feishu] result card send failed: {type(exc).__name__}: {exc}", flush=True)
        fallback = build_error_card(
            f"查询已完成，但结果卡片发送失败（{type(exc).__name__}）。"
            "可重新发送问题，或换一种问法。"
        )
        try:
            if thinking_message_id:
                reply_to_message(thinking_message_id, fallback, reply_in_thread=(chat_type == "group"))
            else:
                _send_card(event, message, chat_id, chat_type, fallback)
        except Exception as inner:
            print(f"[feishu] fallback card also failed: {inner}", flush=True)

    return {"code": 0}


def _handle_user_query_with_limit(
    session_id: str,
    user_text: str,
    query_id: str | None = None,
) -> dict:
    session_semaphore = _get_session_semaphore(session_id)
    if not session_semaphore.acquire(blocking=False):
        if query_id:
            update_query_event(
                query_id,
                status="error",
                error="session busy: previous query is still running",
                duration_ms=0,
            )
        return build_error_card("这个会话上一条查询还在处理，请稍后再发送下一条。")

    if not _query_semaphore.acquire(blocking=False):
        if query_id:
            update_query_event(
                query_id,
                status="error",
                error="service busy: max concurrent queries reached",
                duration_ms=0,
            )
        session_semaphore.release()
        return build_error_card("系统正在处理较多查询，请稍后重试。")

    try:
        return _handle_user_query(session_id, user_text, query_id=query_id)
    finally:
        _query_semaphore.release()
        session_semaphore.release()


def _get_session_semaphore(session_id: str) -> BoundedSemaphore:
    key = session_id or "__default__"
    with _session_semaphores_lock:
        semaphore = _session_semaphores.get(key)
        if semaphore is None:
            semaphore = BoundedSemaphore(1)
            _session_semaphores[key] = semaphore
        return semaphore


@router.post("/feishu/card")
async def feishu_card_callback(request: Request):
    data = await request.json()
    return _handle_card_action(data)


def _handle_card_action(data: dict) -> dict:
    action_value = _extract_action_value(data)
    action = action_value.get("action", "")
    chat_id = (
        data.get("open_chat_id", "")
        or data.get("event", {}).get("open_chat_id", "")
        or data.get("event", {}).get("operator", {}).get("open_chat_id", "")
    )
    print(f"[feishu] card action action={action!r}", flush=True)

    if action == "drill_down":
        card = build_clarification_card("请告诉我你想下钻到哪个维度：ASIN、站点、品类还是日期？")
    elif action == "show_trend":
        card = build_clarification_card("请告诉我趋势的指标和粒度：按天、按周还是按月？")
    elif action == "show_sql":
        card = build_sql_card(action_value.get("sql", ""))
    elif action == "feedback":
        feedback = action_value.get("feedback", "")
        query_id = action_value.get("query_id", "")
        message_id = _extract_card_message_id(data)
        open_id = _extract_operator_open_id(data)
        record_feedback(
            query_id=query_id,
            feedback=feedback or "unknown",
            message_id=message_id,
            open_id=open_id,
            raw_action=action_value,
        )
        card = build_feedback_ack_card(feedback)
    elif action == "reset_session":
        session_id = action_value.get("session_id", "")
        if session_id:
            clear_session(session_id)
            print(
                f"[feishu] session cleared via reset_session button session_id={session_id!r}",
                flush=True,
            )
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "已重置"},
                "template": "grey",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": "上下文已清空。直接发送新问题即可，不会再参考刚才的对话。",
                }
            ],
        }
    else:
        return {"code": 0}

    message_id = _extract_card_message_id(data)
    if message_id:
        reply_to_message(message_id, card, reply_in_thread=True)
    elif chat_id:
        send_card_message(chat_id, "chat_id", card)
    return {"code": 0}


def _extract_action_value(data: dict) -> dict:
    action = data.get("action", {})
    if isinstance(action, dict) and isinstance(action.get("value"), dict):
        return action["value"]

    event = data.get("event", {})
    action = event.get("action", {}) if isinstance(event, dict) else {}
    if isinstance(action, dict):
        if isinstance(action.get("value"), dict):
            return action["value"]
        if isinstance(action.get("value"), str):
            try:
                parsed = json.loads(action["value"])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}

    return {}


def _extract_card_message_id(data: dict) -> str:
    event = data.get("event", {})
    message_id = (
        data.get("open_message_id")
        or data.get("message_id")
        or data.get("container", {}).get("message_id", "")
        or event.get("open_message_id", "")
        or event.get("message_id", "")
        or event.get("context", {}).get("open_message_id", "")
        or event.get("context", {}).get("message_id", "")
    )
    return str(message_id or "")


def _extract_operator_open_id(data: dict) -> str:
    event = data.get("event", {})
    operator = event.get("operator", {}) if isinstance(event, dict) else {}
    operator_id = operator.get("operator_id", {}) if isinstance(operator, dict) else {}
    return str(
        data.get("open_id")
        or operator.get("open_id", "")
        or operator_id.get("open_id", "")
        or ""
    )


def _handle_user_query(session_id: str, user_text: str, query_id: str | None = None) -> dict:
    started = time.monotonic()
    history = get_history(session_id)
    clarification = needs_clarification(user_text, history)
    if clarification.needed:
        add_to_history(session_id, "user", user_text)
        add_to_history(session_id, "assistant", clarification.question)
        if query_id:
            update_query_event(
                query_id,
                status="clarification",
                clarification_reason=clarification.reason,
                clarification_question=clarification.question,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        return build_clarification_card(clarification.question, session_id=session_id)

    selected_docs = select_catalog_table_docs(user_text, history)
    candidate_tables = sorted(_tables_referenced_by_docs(selected_docs))
    selected_tables = _maybe_refine_tables_via_llm(user_text, candidate_tables)
    few_shot_examples = _maybe_find_few_shot_examples(user_text)
    try:
        ai_response = chat(
            build_messages(
                history,
                user_text,
                selected_tables=selected_tables,
                few_shot_examples=few_shot_examples,
            )
        )
    except LLMTimeoutError:
        add_to_history(session_id, "user", user_text)
        if query_id:
            update_query_event(
                query_id,
                status="error",
                selected_catalog_docs=selected_docs,
                error="LLM timeout",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        return build_error_card(
            "AI 服务响应超过 60 秒，已超时。请稍后重试，或换一种更短的问法。"
        )
    except Exception as exc:
        add_to_history(session_id, "user", user_text)
        if query_id:
            update_query_event(
                query_id,
                status="error",
                selected_catalog_docs=selected_docs,
                error=f"LLM error: {type(exc).__name__}: {exc}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        return build_error_card(f"AI 服务调用失败：{type(exc).__name__}")
    add_to_history(session_id, "user", user_text)
    add_to_history(session_id, "assistant", ai_response)

    sql = extract_sql(ai_response)
    if not sql:
        if query_id:
            update_query_event(
                query_id,
                status="llm_clarification",
                selected_catalog_docs=selected_docs,
                llm_response=ai_response,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        return build_clarification_card(ai_response, session_id=session_id)

    data_rows, columns, error = execute_query(sql)
    repair_response = ""
    if error:
        repaired_sql, repair_response = _repair_sql_via_llm(
            user_text=user_text,
            sql=sql,
            error=error,
            history=history,
            selected_tables=selected_tables,
            few_shot_examples=few_shot_examples,
        )
        if repaired_sql:
            retry_rows, retry_columns, retry_error = execute_query(repaired_sql)
            if retry_error is None:
                sql = repaired_sql
                data_rows = retry_rows
                columns = retry_columns
                error = None
            else:
                error = f"{error}\n\n重试 SQL 仍出错：{retry_error}"

    if error:
        if query_id:
            update_query_event(
                query_id,
                status="error",
                selected_catalog_docs=selected_docs,
                llm_response=ai_response + (f"\n\n# SQL repair attempt\n{repair_response}" if repair_response else ""),
                sql=sql,
                error=error,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        return build_error_card(f"SQL 执行出错：{error}\n\n```sql\n{sql}\n```")

    from data_agent.visualization.chart import (
        choose_chart_columns,
        data_to_markdown_table,
        generate_bar_chart,
        generate_line_chart,
        infer_metric_column,
        is_time_series_chart,
        parse_order_by_column,
    )

    image_key = None
    intent = infer_query_intent(user_text)
    table_max_rows = intent.table_max_rows
    prefer_y = infer_metric_column(user_text, columns) or parse_order_by_column(sql)
    chart_cols = choose_chart_columns(data_rows, columns, prefer_y=prefer_y)
    if chart_cols:
        x_col, y_col = chart_cols
        chart_bytes = None
        if intent.chart_type == "line" or is_time_series_chart(user_text, x_col, len(data_rows)):
            table_max_rows = 31
            chart_bytes = generate_line_chart(
                data_rows,
                x_col=x_col,
                y_cols=[y_col],
                title=user_text[:30],
            )
        elif intent.chart_type != "table":
            chart_bytes = generate_bar_chart(
                data_rows,
                x_col=x_col,
                y_col=y_col,
                title=user_text[:30],
                y_label=y_col,
            )
        if chart_bytes:
            image_key = upload_image(chart_bytes)

    if query_id:
        update_query_event(
            query_id,
            status="success",
            selected_catalog_docs=selected_docs,
            llm_response=ai_response + (f"\n\n# SQL repair attempt\n{repair_response}" if repair_response else ""),
            sql=sql,
            row_count=len(data_rows),
            columns_json=columns,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    if not data_rows:
        return build_empty_result_card(
            title=user_text[:80] or "查询结果",
            summary=strip_sql_blocks(ai_response),
            sql=sql,
            query_id=query_id,
        )

    return build_result_card(
        title=user_text[:80] or "查询结果",
        summary=strip_sql_blocks(ai_response),
        table_markdown=data_to_markdown_table(data_rows, columns, max_rows=table_max_rows),
        image_key=image_key,
        sql=sql,
        query_id=query_id,
        table_rows=data_rows,
        columns=columns,
        table_max_rows=table_max_rows,
    )


def _extract_user_text(message: dict) -> str:
    content_raw = message.get("content") or "{}"
    try:
        content = json.loads(content_raw)
    except json.JSONDecodeError:
        return ""

    text = content.get("text", "").strip()
    return re.sub(r"<at[^>]*>.*?</at>", "", text).strip()


def _message_routing(message: dict) -> tuple[bool, str]:
    chat_type = message.get("chat_type", "")
    chat_id = message.get("chat_id", "")
    message_id = message.get("message_id", "")
    thread_id = message.get("thread_id") or ""

    if chat_type != "group":
        return True, thread_id or chat_id or message_id

    if thread_id and thread_id in _active_group_threads:
        return True, thread_id

    if _message_mentions_bot(message):
        session_id = thread_id or message_id or chat_id
        if session_id:
            _active_group_threads.add(session_id)
        return True, session_id

    return False, ""


def _message_mentions_bot(message: dict) -> bool:
    try:
        bot_open_id = get_bot_open_id()
    except Exception as exc:
        print(f"[feishu] bot identity lookup failed: {exc}", flush=True)
        return False

    for mention in message.get("mentions") or []:
        mention_id = mention.get("id", {}) if isinstance(mention, dict) else {}
        if bot_open_id in {
            mention_id.get("open_id", ""),
            mention_id.get("user_id", ""),
            mention.get("open_id", "") if isinstance(mention, dict) else "",
        }:
            return True

    content_raw = message.get("content") or ""
    return bot_open_id in content_raw


def _maybe_refine_tables_via_llm(user_text: str, candidate_tables: list[str]) -> list[str] | None:
    """PD-2: when keyword selection is ambiguous (multiple docs hit and the
    candidate pool is wide), ask the LLM to narrow it down. Returns None for
    the caller to fall through to keyword-derived tables when LLM refine is
    skipped or fails.
    """
    # Only worth a round-trip when the pool is wide: >2 candidate tables
    # spanning more than one domain. Single-domain queries don't benefit.
    if len(candidate_tables) <= 2:
        return None
    try:
        refined = refine_tables_via_llm(user_text, candidate_tables)
    except Exception as exc:
        print(f"[pd2] refine skipped: {type(exc).__name__}: {exc}", flush=True)
        return None
    if refined and set(refined) != set(candidate_tables):
        print(
            f"[pd2] refined {len(candidate_tables)} → {len(refined)} tables: {refined}",
            flush=True,
        )
        return refined
    return None


def _maybe_find_few_shot_examples(user_text: str, limit: int = 2) -> list[dict]:
    """PD-5: find up to `limit` past successful question/SQL pairs whose
    question resembles `user_text`. Failures here are non-fatal — return []
    so the main flow proceeds without few-shot.
    """
    try:
        from data_agent.agent.query_examples import find_similar_success_queries

        return find_similar_success_queries(user_text, limit=limit)
    except Exception as exc:
        print(f"[pd5] few-shot lookup failed: {type(exc).__name__}: {exc}", flush=True)
        return []


def _send_initial_feedback(event: dict, message: dict, chat_id: str, chat_type: str) -> str | None:
    try:
        return _send_card(event, message, chat_id, chat_type, build_thinking_card())
    except Exception as exc:
        print(f"[feishu] initial feedback skipped: {exc}")
        return None


def _send_card(event: dict, message: dict, chat_id: str, chat_type: str, card: dict) -> str | None:
    if chat_type == "group" and chat_id:
        message_id = message.get("message_id", "")
        if message_id:
            return reply_to_message(message_id, card, reply_in_thread=True)
        return None

    open_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")
    if open_id:
        return send_card_message(open_id, "open_id", card)
    return None
